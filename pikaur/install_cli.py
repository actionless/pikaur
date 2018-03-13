import platform
import sys
import os
from tempfile import NamedTemporaryFile
from typing import List, Dict, Union, Tuple

import pyalpm

from .args import reconstruct_args, PikaurArgs
from .aur import find_aur_packages
from .aur_deps import find_aur_deps
from .i18n import _
from .pacman import (
    find_repo_packages, PackageDB, OFFICIAL_REPOS, PacmanConfig,
)
from .package_update import PackageUpdate, get_remote_package_version
from .exceptions import (
    PackagesNotFoundInAUR, DependencyVersionMismatch,
    BuildError, CloneError, DependencyError, DependencyNotBuiltYet,
)
from .build import (
    SrcInfo, PackageBuild,
    clone_pkgbuilds_git_repos,
)
from .pprint import (
    color_line, bold_line,
    pretty_format_sysupgrade, pretty_format_upgradeable,
    print_not_found_packages,
)
from .core import (
    CmdTaskWorker, PackageSource,
    interactive_spawn, remove_dir,
)
from .async import SingleTaskExecutor
from .replacements import (
    find_replacements,
)
from .prompt import (
    ask_to_continue, retry_interactive_command,
    retry_interactive_command_or_exit,
)


def exclude_ignored_packages(package_names: List[str], args: PikaurArgs) -> List[str]:
    excluded_pkgs = []
    for ignored_pkg in (args.ignore or []) + PacmanConfig().options.get('IgnorePkg', []):
        if ignored_pkg in package_names:
            package_names.remove(ignored_pkg)
            excluded_pkgs.append(ignored_pkg)
    return excluded_pkgs


class InstallPackagesCLI():

    args: PikaurArgs = None
    repo_packages: List[pyalpm.Package] = None
    repo_packages_names: List[str] = None  # @TODO: remove me
    aur_packages_names: List[str] = None
    aur_deps_names: List[str] = None
    package_builds: Dict[str, PackageBuild] = None
    failed_to_build: List[str] = None
    transactions: Dict[str, Dict[str, List[str]]] = None

    def __init__(self, args: PikaurArgs, packages: List[str] = None) -> None:
        self.args = args

        packages = packages or args.positional
        self.exclude_ignored_packages(packages)
        if not packages:
            print('{} {}'.format(
                color_line('::', 10),
                _("Nothing to do."),
            ))
            return
        self.find_packages(packages)

        self.install_prompt()

        self.get_package_builds()
        # @TODO: ask to install optdepends (?)
        if not args.downloadonly:
            self.ask_about_package_replacements()
        self.review_build_files()

        # get sudo for further questions (command should do nothing):
        interactive_spawn(['sudo', 'pacman', '-T'])

        self.build_packages()

        self.install_repo_packages()
        if not args.downloadonly:
            self.install_new_aur_deps()
            self.install_aur_packages()

        # save git hash of last sucessfully installed package
        if self.package_builds:
            for package_build in self.package_builds.values():
                if package_build.built_package_path:
                    if not args.downloadonly:
                        package_build.update_last_installed_file()
                    remove_dir(package_build.build_dir)

        if self.failed_to_build:
            print('\n'.join(
                [color_line(_("Failed to build following packages:"), 9), ] +
                self.failed_to_build
            ))

    @property
    def all_aur_packages_names(self) -> List[str]:
        return self.aur_packages_names + self.aur_deps_names

    def get_editor(self) -> Union[List[str], None]:
        editor_line = os.environ.get('VISUAL') or os.environ.get('EDITOR')
        if editor_line:
            return editor_line.split(' ')
        for editor in ('vim', 'nano', 'mcedit', 'edit'):
            result = SingleTaskExecutor(
                CmdTaskWorker(['which', editor])
            ).execute()
            if result.return_code == 0:
                return [editor, ]
        print(
            '{} {}'.format(
                color_line('error:', 9),
                _("no editor found. Try setting $VISUAL or $EDITOR.")
            )
        )
        if not self.ask_to_continue(_("Do you want to proceed without editing?")):
            sys.exit(2)
        return None

    def exclude_ignored_packages(self, packages: List[str]) -> None:
        excluded_packages = exclude_ignored_packages(packages, self.args)
        for package_name in excluded_packages:
            current = PackageDB.get_local_dict().get(package_name)
            current_version = current.version if current else ''
            new_version = get_remote_package_version(package_name)
            print('{} {}'.format(
                color_line('::', 11),
                _("Ignoring package {}").format(
                    pretty_format_upgradeable(
                        [PackageUpdate(
                            Name=package_name,
                            Current_Version=current_version,
                            New_Version=new_version or ''
                        )],
                        template=(
                            "{pkg_name} ({current_version} => {new_version})"
                            if current_version else
                            "{pkg_name} {new_version}"
                        )
                    ))
            ))

    def find_packages(self, packages: List[str]) -> None:
        print(_("resolving dependencies..."))
        self.repo_packages, self.aur_packages_names = find_repo_packages(
            packages
        )
        self.repo_packages_names = [pkg.name for pkg in self.repo_packages]
        try:
            self.aur_deps_names = find_aur_deps(self.aur_packages_names)
        except PackagesNotFoundInAUR as exc:
            if exc.wanted_by:
                print("{} {}".format(
                    color_line(':: error:', 9),
                    bold_line(
                        _("Dependencies missing for {}").format(exc.wanted_by))
                ))
            print_not_found_packages(exc.packages)
            sys.exit(1)
        except DependencyVersionMismatch as exc:
            print(color_line(_("Version mismatch:"), 11))
            print(_("{what} depends on: '{dep}'\n found in '{location}': '{version}'").format(
                what=bold_line(exc.who_depends),
                dep=exc.dependency_line,
                location=exc.location,
                version=exc.version_found,
            ))
            sys.exit(1)

    def _get_repo_pkgs_updates(self) -> Tuple[List[PackageUpdate], List[PackageUpdate]]:
        local_pkgs = PackageDB.get_local_dict()
        repo_packages_updates = []
        thirdparty_repo_packages_updates = []
        for repo_pkg in self.repo_packages:
            pkg_name = repo_pkg.name
            local_pkg = local_pkgs.get(pkg_name)
            pkg = PackageUpdate(
                Name=pkg_name,
                Current_Version=local_pkg.version if local_pkg else ' ',
                New_Version=repo_pkg.version,
                Description=repo_pkg.desc,
                Repository=repo_pkg.db.name
            )
            if repo_pkg.db.name in OFFICIAL_REPOS:
                repo_packages_updates.append(pkg)
            else:
                thirdparty_repo_packages_updates.append(pkg)
        return repo_packages_updates, thirdparty_repo_packages_updates

    def _get_aur_updates(self) -> List[PackageUpdate]:
        local_pkgs = PackageDB.get_local_dict()
        aur_pkgs = {
            aur_pkg.name: aur_pkg
            for aur_pkg in find_aur_packages(
                self.aur_packages_names
            )[0]
        }
        aur_updates = []
        for pkg_name in self.aur_packages_names:
            aur_pkg = aur_pkgs[pkg_name]
            local_pkg = local_pkgs.get(pkg_name)
            aur_updates.append(PackageUpdate(
                Name=pkg_name,
                Current_Version=local_pkg.version if local_pkg else ' ',
                New_Version=aur_pkg.version,
                Description=aur_pkg.desc
            ))
        return aur_updates

    def _get_aur_deps(self) -> List[PackageUpdate]:
        local_pkgs = PackageDB.get_local_dict()
        aur_pkgs = {
            aur_pkg.name: aur_pkg
            for aur_pkg in find_aur_packages(
                self.aur_deps_names
            )[0]
        }
        aur_deps = []
        for pkg_name in self.aur_deps_names:
            aur_pkg = aur_pkgs[pkg_name]
            local_pkg = local_pkgs.get(pkg_name)
            aur_deps.append(PackageUpdate(
                Name=pkg_name,
                Current_Version=local_pkg.version if local_pkg else ' ',
                New_Version=aur_pkg.version,
                Description=aur_pkg.desc
            ))
        return aur_deps

    def manual_package_selection(self, text: str) -> List[str]:
        selected_packages = []
        with NamedTemporaryFile() as tmp_file:
            with open(tmp_file.name, 'w') as write_file:
                write_file.write(text)
            interactive_spawn(
                self.get_editor() + [tmp_file.name, ]
            )
            with open(tmp_file.name, 'r') as read_file:
                for line in read_file.readlines():
                    line = line.lstrip()
                    if not line:
                        continue
                    if not line.startswith('::') and not line.startswith('#'):
                        pkg_name = line.split()[0]
                        if '/' in pkg_name:
                            pkg_name = pkg_name.split('/')[1]
                        selected_packages.append(pkg_name)
        return selected_packages

    def install_prompt(self) -> None:
        repo_packages_updates, thirdparty_repo_packages_updates = \
            self._get_repo_pkgs_updates()
        aur_updates = self._get_aur_updates()
        aur_deps = self._get_aur_deps()

        def _print_sysupgrade(verbose=False) -> None:
            print(pretty_format_sysupgrade(
                repo_packages_updates, thirdparty_repo_packages_updates,
                aur_updates, aur_deps,
                verbose=verbose
            ))

        def _confirm_sysupgrade(verbose=False) -> str:
            _print_sysupgrade(verbose=verbose)
            answer = input('{} {}\n{} {}\n> '.format(
                color_line('::', 12),
                bold_line(_("Proceed with installation? [Y/n]")),
                color_line('::', 12),
                bold_line(_("[v]iew package detail   [m]anually select packages"))
            ))
            return answer

        if self.args.noconfirm:
            _print_sysupgrade()
            return
        answer = None
        while True:
            if answer is None:
                answer = _confirm_sysupgrade()
            if answer:
                letter = answer.lower()[0]
                if letter == _("y"):
                    break
                elif letter == _("v"):
                    answer = _confirm_sysupgrade(verbose=True)
                elif letter == _("m"):
                    print()
                    packages = self.manual_package_selection(
                        text=pretty_format_sysupgrade(
                            repo_packages_updates, thirdparty_repo_packages_updates,
                            aur_updates,
                            color=False
                        )
                    )
                    self.find_packages(packages)
                    self.install_prompt()
                    break
                else:
                    sys.exit(1)
            else:
                break

    def get_package_builds(self) -> None:
        if not self.all_aur_packages_names:
            self.package_builds = {}
            return
        while self.all_aur_packages_names:
            try:
                self.package_builds = clone_pkgbuilds_git_repos(self.all_aur_packages_names)
                break
            except CloneError as err:
                package_build = err.build
                print(color_line((
                    _("Can't clone '{name}' in '{path}' from AUR:")
                    if package_build.clone else
                    _("Can't pull '{name}' in '{path}' from AUR:")).format(
                        name=package_build.package_name,
                        path=package_build.repo_path
                    ), 9))
                print(err.result)
                if self.args.noconfirm:
                    answer = _("a")
                else:
                    answer = input('{} {}\n{}\n{}\n{}\n{}\n> '.format(
                        color_line('::', 11),
                        _("Try recovering?"),
                        _("[c] git checkout -- '*'"),
                        # _("[c] git checkout -- '*' ; git clean -f -d -x"),
                        _("[r] remove dir and clone again"),
                        _("[s] skip this package"),
                        _("[a] abort"),
                        ))
                answer = answer.lower()[0]
                if answer == _("c"):
                    package_build.git_reset_changed()
                elif answer == _("r"):
                    remove_dir(package_build.repo_path)
                elif answer == _("s"):
                    if package_build.package_name in self.aur_packages_names:
                        self.aur_packages_names.remove(package_build.package_name)
                    else:
                        self.aur_deps_names.remove(package_build.package_name)
                else:
                    sys.exit(1)

    def ask_to_continue(self, text: str = None, default_yes=True) -> bool:
        return ask_to_continue(text, default_yes, args=self.args)

    def ask_about_package_replacements(self) -> None:
        package_replacements = find_replacements()
        for repo_pkg_name, installed_pkgs_names in package_replacements.items():
            for installed_pkg_name in installed_pkgs_names:
                if self.ask_to_continue(
                        '{} {}'.format(
                            color_line('::', 11),
                            _("New package '{new}' replaces installed '{installed}' "
                              "Proceed?").format(
                                  new=bold_line(repo_pkg_name),
                                  installed=bold_line(installed_pkg_name))
                        ), default_yes=False
                ):
                    self.repo_packages_names.append(repo_pkg_name)

    def ask_to_edit_file(self, filename: str, package_build: PackageBuild) -> bool:
        if self.args.noedit or self.args.noconfirm:
            print('{} {}'.format(
                color_line('::', 11),
                _("Skipping review of {file} for {name} package ({flag})").format(
                    file=filename,
                    name=package_build.package_name,
                    flag=(self.args.noedit and '--noedit') or
                    (self.args.noconfirm and '--noconfirm')),
            ))
            return False
        if self.ask_to_continue(
                _("Do you want to {edit} {file} for {name} package?").format(
                    edit=bold_line(_("edit")),
                    file=filename,
                    name=bold_line(package_build.package_name),
                ),
                default_yes=not package_build.is_installed
        ):
            interactive_spawn(
                self.get_editor() + [
                    os.path.join(
                        package_build.repo_path,
                        filename
                    )
                ]
            )
            return True
        return False

    def review_build_files(self) -> None:
        for pkg_name in self.all_aur_packages_names:
            repo_status = self.package_builds[pkg_name]
            if self.args.needed and repo_status.version_already_installed:
                print(
                    '{} {}'.format(
                        color_line(_("warning:"), 11),
                        _("{name} is up to date -- skipping").format(name=pkg_name)))
                return
            if repo_status.build_files_updated and not self.args.noconfirm:
                if self.ask_to_continue(
                        _("Do you want to see build files {diff} for {name} package?").format(
                            diff=bold_line(_("diff")),
                            name=bold_line(pkg_name)
                        )
                ):
                    interactive_spawn([
                        'git',
                        '-C',
                        repo_status.repo_path,
                        'diff',
                        repo_status.last_installed_hash,
                        repo_status.current_hash,
                    ])
            src_info = SrcInfo(repo_status.repo_path, pkg_name)

            if self.get_editor():
                if self.ask_to_edit_file('PKGBUILD', repo_status):
                    src_info.regenerate()
                    # @TODO: recompute AUR deps
                install_file_name = src_info.get_install_script()
                if install_file_name:
                    self.ask_to_edit_file(install_file_name, repo_status)

            arch = platform.machine()
            supported_archs = src_info.get_values('arch')
            if supported_archs and (
                    'any' not in supported_archs
            ) and (
                arch not in supported_archs
            ):
                print("{} {}".format(
                    color_line(':: error:', 9),
                    _("{name} can't be built on the current arch ({arch}). "
                      "Supported: {suparch}").format(
                          name=bold_line(pkg_name),
                          arch=arch,
                          suparch=', '.join(supported_archs))
                ))
                sys.exit(1)

    def build_packages(self) -> None:
        failed_to_build = []
        deps_fails_counter: Dict[str, int] = {}
        packages_to_be_built = self.all_aur_packages_names[:]
        index = 0
        while packages_to_be_built:
            if index >= len(packages_to_be_built):
                index = 0

            pkg_name = packages_to_be_built[index]
            repo_status = self.package_builds[pkg_name]
            if self.args.needed and repo_status.already_installed:
                packages_to_be_built.remove(pkg_name)
                continue

            try:
                repo_status.build(self.args, self.package_builds)
            except (BuildError, DependencyError) as exc:
                print(exc)
                print(color_line(_("Can't build '{name}'.").format(name=pkg_name), 9))
                failed_to_build.append(pkg_name)
                # if not self.ask_to_continue():
                #     sys.exit(1)
                packages_to_be_built.remove(pkg_name)
            except DependencyNotBuiltYet:
                index += 1
                deps_fails_counter.setdefault(pkg_name, 0)
                deps_fails_counter[pkg_name] += 1
                if deps_fails_counter[pkg_name] > len(self.all_aur_packages_names):
                    print('{} {}'.format(
                        color_line(":: " + _("error:"), 9),
                        _("Dependency cycle detected between {}").format(deps_fails_counter)
                    ))
                    sys.exit(1)
            else:
                packages_to_be_built.remove(pkg_name)

        self.failed_to_build = failed_to_build

    def _remove_packages(self, packages_to_be_removed: List[str]) -> None:
        # pylint: disable=no-self-use
        if packages_to_be_removed:
            retry_interactive_command_or_exit(
                [
                    'sudo',
                    'pacman',
                    '-Rs',
                ] + packages_to_be_removed,
            )

    def _install_repo_packages(self, packages_to_be_installed: List[str]) -> None:
        if self.repo_packages_names:
            if not retry_interactive_command(
                    [
                        'sudo',
                        'pacman',
                        '--sync',
                        '--ask=no',
                    ] + reconstruct_args(self.args, ignore_args=[
                        'sync',
                        'sysupgrade',
                        'refresh',
                        'ignore',
                    ]) + packages_to_be_installed,
            ):
                if not self.ask_to_continue(default_yes=False):
                    self.revert_repo_transaction()
                    sys.exit(1)

    def _save_transaction(
            self,
            target: PackageSource,
            removed: List[str] = None,
            installed: List[str] = None
    ) -> None:
        if not self.transactions:
            self.transactions = {}
        target_transaction = self.transactions.setdefault(str(target), {})
        if removed:
            for pkg_name in removed:
                target_transaction.setdefault('removed', []).append(pkg_name)
        if installed:
            for pkg_name in installed:
                target_transaction.setdefault('installed', []).append(pkg_name)

    def save_repo_transaction(self, removed: List[str] = None, installed: List[str] = None) -> None:
        self._save_transaction(
            PackageSource.REPO, removed=removed, installed=installed
        )

    def save_aur_transaction(self, removed: List[str] = None, installed: List[str] = None) -> None:
        self._save_transaction(
            PackageSource.AUR, removed=removed, installed=installed
        )

    def _revert_transaction(self, target: PackageSource) -> None:
        if not self.transactions:
            return
        target_transaction = self.transactions.get(str(target))
        if not target_transaction:
            return
        print('{} {}'.format(
            color_line('::', 9),
            _("Reverting {target} transaction...").format(target=target)
        ))
        removed = target_transaction.get('removed')
        installed = target_transaction.get('installed')
        if removed:
            pass  # install back
        if installed:
            self._remove_packages(installed)

    def revert_repo_transaction(self) -> None:
        self._revert_transaction(PackageSource.REPO)

    def revert_aur_transaction(self) -> None:
        self._revert_transaction(PackageSource.AUR)

    def install_repo_packages(self) -> None:
        self._install_repo_packages(self.repo_packages_names)
        self.save_repo_transaction(self.repo_packages_names)

    def install_new_aur_deps(self) -> None:
        new_aur_deps_to_install = [
            self.package_builds[pkg_name].built_package_path
            for pkg_name in self.aur_deps_names
            if self.package_builds[pkg_name].built_package_path and
            not self.package_builds[pkg_name].built_package_installed
        ]
        if new_aur_deps_to_install:
            if not retry_interactive_command(
                    [
                        'sudo',
                        'pacman',
                        '--upgrade',
                        '--asdeps',
                        '--ask=no',
                    ] + reconstruct_args(self.args, ignore_args=[
                        'upgrade',
                        'asdeps',
                        'sync',
                        'sysupgrade',
                        'refresh',
                        'ignore',
                    ]) + new_aur_deps_to_install,
            ):
                if not self.ask_to_continue(default_yes=False):
                    self.revert_aur_transaction()
                    sys.exit(1)
            self.save_aur_transaction(new_aur_deps_to_install)

    def install_aur_packages(self) -> None:
        aur_packages_to_install = [
            self.package_builds[pkg_name].built_package_path
            for pkg_name in self.aur_packages_names
            if self.package_builds[pkg_name].built_package_path
        ]
        if aur_packages_to_install:
            if not retry_interactive_command(
                    [
                        'sudo',
                        'pacman',
                        '--upgrade',
                        '--ask=no',
                    ] + reconstruct_args(self.args, ignore_args=[
                        'upgrade',
                        'sync',
                        'sysupgrade',
                        'refresh',
                        'ignore',
                    ]) + aur_packages_to_install,
            ):
                if not self.ask_to_continue(default_yes=False):
                    self.revert_aur_transaction()
                    sys.exit(1)
            self.save_aur_transaction(aur_packages_to_install)
