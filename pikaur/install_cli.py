import platform
import sys
import os
from tempfile import NamedTemporaryFile
from typing import List, Dict, Union

import pyalpm

from .config import PikaurConfig
from .args import reconstruct_args, PikaurArgs
from .aur import find_aur_packages
from .aur_deps import find_aur_deps
from .i18n import _
from .pacman import (
    OFFICIAL_REPOS,
    PackageDB, PacmanConfig, get_pacman_command,
    find_repo_packages,
)
from .package_update import (
    PackageUpdate, get_remote_package_version,
    find_aur_updates, find_repo_updates,
)
from .exceptions import (
    PackagesNotFoundInAUR, DependencyVersionMismatch,
    BuildError, CloneError, DependencyError, DependencyNotBuiltYet,
)
from .build import (
    PackageBuild,
    clone_aur_repos,
)
from .pprint import (
    color_line, bold_line,
    pretty_format_sysupgrade, pretty_format_upgradeable,
    print_not_found_packages, print_status_message,
)
from .core import (
    PackageSource,
    spawn, interactive_spawn, remove_dir, open_file,
)
from .conflicts import find_conflicts
from .prompt import (
    ask_to_continue, retry_interactive_command,
    retry_interactive_command_or_exit, get_input,
)
from .srcinfo import SrcInfo


def package_is_ignored(package_name: str, args: PikaurArgs) -> bool:
    if package_name in (args.ignore or []) + PacmanConfig().options.get('IgnorePkg', []):
        return True
    return False


def exclude_ignored_packages(package_names: List[str], args: PikaurArgs) -> List[str]:
    excluded_pkgs = []
    for pkg_name in package_names[:]:
        if package_is_ignored(pkg_name, args=args):
            package_names.remove(pkg_name)
            excluded_pkgs.append(pkg_name)
    return excluded_pkgs


def print_ignored_package(package_name):
    current = PackageDB.get_local_dict().get(package_name)
    current_version = current.version if current else ''
    new_version = get_remote_package_version(package_name)
    print_status_message('{} {}'.format(
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


def print_package_uptodate(package_name: str, package_source: PackageSource) -> None:
    print_status_message(
        '{} {}'.format(
            color_line(_("warning:"), 11),
            _("{name} {version} {package_source} package is up to date - skipping").format(
                name=package_name,
                version=bold_line(
                    PackageDB.get_local_dict()[package_name].version
                ),
                package_source=package_source.name
            )
        )
    )


class InstallPackagesCLI():
    # @TODO: refactor this warning:
    # pylint: disable=too-many-public-methods,too-many-instance-attributes

    # User input
    args: PikaurArgs = None
    install_package_names: List[str] = None
    manually_excluded_packages_names: List[str] = None

    # computed package lists:
    repo_packages_by_name: Dict[str, pyalpm.Package] = None
    aur_deps_relations: Dict[str, List[str]] = None
    # pkgbuilds from cloned aur repos:
    package_builds_by_name: Dict[str, PackageBuild] = None

    # Packages' install info
    # @TODO: refactor this and related methods
    #        into separate class InstallPrompt? (PackageSelection?)
    repo_packages_install_info: List[PackageUpdate] = None
    thirdparty_repo_packages_install_info: List[PackageUpdate] = None
    aur_updates_install_info: List[PackageUpdate] = None
    aur_deps_install_info: List[PackageUpdate] = None

    # Installation results
    # transactions by PackageSource(AUR/repo), direction(removed/installed):
    transactions: Dict[str, Dict[str, List[str]]] = None
    # AUR packages which failed to build:
    # @TODO: refactor to store in transactions
    failed_to_build_package_names: List[str] = None

    def __init__(self, args: PikaurArgs, packages: List[str] = None) -> None:
        self.args = args
        self.install_package_names = packages or args.positional
        self.manually_excluded_packages_names = []
        self.install_packages()

    def install_packages(self):
        args = self.args
        self.get_all_packages_info()
        self.install_prompt()

        self.get_package_builds()
        # @TODO: ask to install optdepends (?)
        if not args.downloadonly:
            self.ask_about_package_conflicts()
        self.review_build_files()
        if not (self.install_package_names or self.args.sysupgrade):
            return

        # get sudo for further questions (command should do nothing):
        interactive_spawn(['sudo', 'pacman', '-T'])

        self.install_repo_packages()

        self.build_packages()
        if not args.downloadonly:
            self.install_new_aur_deps()
            self.install_aur_packages()

        # save git hash of last sucessfully installed package
        if self.package_builds_by_name:
            package_builds_by_base = {
                pkgbuild.package_base: pkgbuild
                for pkgbuild in self.package_builds_by_name.values()
            }
            for package_build in package_builds_by_base.values():
                if len(package_build.built_packages_paths) == len(package_build.package_names):
                    if not args.downloadonly:
                        package_build.update_last_installed_file()
                    if not (args.keepbuild or PikaurConfig().build.get('KeepBuildDir')):
                        remove_dir(package_build.build_dir)

        if self.failed_to_build_package_names:
            print_status_message('\n'.join(
                [color_line(_("Failed to build following packages:"), 9), ] +
                self.failed_to_build_package_names
            ))
            sys.exit(1)

    @property
    def aur_packages_names(self) -> List[str]:
        return list(self.aur_deps_relations.keys())

    @property
    def aur_deps_names(self) -> List[str]:
        _aur_deps_names: List[str] = []
        for deps in self.aur_deps_relations.values():
            _aur_deps_names += deps
        return list(set(_aur_deps_names))

    @property
    def all_aur_packages_names(self) -> List[str]:
        return list(set(self.aur_packages_names + self.aur_deps_names))

    def get_editor(self) -> Union[List[str], None]:
        editor_line = os.environ.get('VISUAL') or os.environ.get('EDITOR')
        if editor_line:
            return editor_line.split(' ')
        for editor in ('vim', 'nano', 'mcedit', 'edit'):
            result = spawn(['which', editor])
            if result.returncode == 0:
                return [editor, ]
        print_status_message(
            '{} {}'.format(
                color_line('error:', 9),
                _("no editor found. Try setting $VISUAL or $EDITOR.")
            )
        )
        if not self.ask_to_continue(_("Do you want to proceed without editing?")):
            sys.exit(125)
        return None

    def exclude_ignored_packages(self) -> None:
        ignored_packages = exclude_ignored_packages(self.install_package_names, self.args)
        for package_name in ignored_packages:
            print_ignored_package(package_name)
        for package_name in self.manually_excluded_packages_names:
            if package_name in self.install_package_names:
                print_ignored_package(package_name)
                self.install_package_names.remove(package_name)

    def exlude_already_uptodate(self) -> None:
        if self.args.needed:
            repo_updates = find_repo_updates()
            for package_name in list(self.repo_packages_by_name.keys())[:]:
                if package_name not in repo_updates:
                    del self.repo_packages_by_name[package_name]
                    if package_name in self.install_package_names:
                        self.install_package_names.remove(package_name)
                    print_package_uptodate(package_name, PackageSource.REPO)

    def get_all_packages_info(self) -> None:
        self.exclude_ignored_packages()
        repo_packages, all_aur_packages_names = find_repo_packages(
            self.install_package_names
        )
        if self.args.aur:
            repo_packages = []
        if self.args.repo:
            all_aur_packages_names = []
        self.repo_packages_by_name = {pkg.name: pkg for pkg in repo_packages}
        self.exlude_already_uptodate()

        self.get_repo_pkgs_info()
        self.get_aur_pkgs_info(all_aur_packages_names)
        if not (
                self.repo_packages_install_info or
                self.thirdparty_repo_packages_install_info or
                self.aur_updates_install_info
        ):
            if self.args.sysupgrade:
                self._install_repo_packages([])
            else:
                print('{} {}'.format(
                    color_line('::', 10),
                    _("Nothing to do."),
                ))
            sys.exit(0)

        try:
            self.get_aur_deps_info()
        except PackagesNotFoundInAUR as exc:
            if exc.wanted_by:
                print_status_message("{} {}".format(
                    color_line(':: error:', 9),
                    bold_line(
                        _("Dependencies missing for {}").format(exc.wanted_by))
                ))
            print_not_found_packages(exc.packages)
            sys.exit(131)
        except DependencyVersionMismatch as exc:
            print_status_message(color_line(_("Version mismatch:"), 11))
            print_status_message(
                _("{what} depends on: '{dep}'\n found in '{location}': '{version}'").format(
                    what=bold_line(exc.who_depends),
                    dep=exc.dependency_line,
                    location=exc.location,
                    version=exc.version_found,
                )
            )
            sys.exit(131)

    def get_repo_pkgs_info(self):
        local_pkgs = PackageDB.get_local_dict()
        repo_packages_install_info_by_name = {
            upd.Name: upd for upd in find_repo_updates()
        } if self.args.sysupgrade else {}

        for repo_pkg in self.repo_packages_by_name.values():
            pkg_name = repo_pkg.name
            if pkg_name in repo_packages_install_info_by_name:
                continue
            local_pkg = local_pkgs.get(pkg_name)
            repo_packages_install_info_by_name[pkg_name] = PackageUpdate(
                Name=pkg_name,
                Current_Version=local_pkg.version if local_pkg else ' ',
                New_Version=repo_pkg.version,
                Description=repo_pkg.desc,
                Repository=repo_pkg.db.name
            )

        self.repo_packages_install_info = []
        self.thirdparty_repo_packages_install_info = []
        for pkg_name, pkg_update in repo_packages_install_info_by_name.items():
            if (
                    pkg_name in self.manually_excluded_packages_names
            ) or (
                package_is_ignored(pkg_name, args=self.args)
            ):
                print_ignored_package(pkg_name)
                continue
            if pkg_update.Repository in OFFICIAL_REPOS:
                self.repo_packages_install_info.append(pkg_update)
            else:
                self.thirdparty_repo_packages_install_info.append(pkg_update)

    def get_aur_pkgs_info(self, aur_packages_names: List[str]):
        local_pkgs = PackageDB.get_local_dict()
        aur_pkg_list, not_found_aur_pkgs = find_aur_packages(aur_packages_names)
        if not_found_aur_pkgs:
            print_not_found_packages(sorted(not_found_aur_pkgs))
            sys.exit(6)
        aur_pkgs = {
            aur_pkg.name: aur_pkg
            for aur_pkg in aur_pkg_list
        }
        aur_updates_install_info_by_name: Dict[str, PackageUpdate] = {}
        if self.args.sysupgrade:
            aur_updates_list, not_found_aur_pkgs = find_aur_updates(self.args)
            exclude_ignored_packages(not_found_aur_pkgs, self.args)
            if not_found_aur_pkgs:
                print_not_found_packages(sorted(not_found_aur_pkgs))
            aur_updates_install_info_by_name = {
                upd.Name: upd for upd in aur_updates_list
            }
        for pkg_name, aur_pkg in aur_pkgs.items():
            if pkg_name in aur_updates_install_info_by_name:
                continue
            local_pkg = local_pkgs.get(pkg_name)
            aur_updates_install_info_by_name[pkg_name] = PackageUpdate(
                Name=pkg_name,
                Current_Version=local_pkg.version if local_pkg else ' ',
                New_Version=aur_pkg.version,
                Description=aur_pkg.desc
            )
        for pkg_name in list(aur_updates_install_info_by_name.keys())[:]:
            if (
                    pkg_name in self.manually_excluded_packages_names
            ) or (
                package_is_ignored(pkg_name, args=self.args)
            ):
                print_ignored_package(pkg_name)
                del aur_updates_install_info_by_name[pkg_name]
        self.aur_updates_install_info = list(aur_updates_install_info_by_name.values())

    def get_aur_deps_info(self):
        all_aur_packages_names = [info.Name for info in self.aur_updates_install_info]
        if all_aur_packages_names:
            print(_("Resolving AUR dependencies..."))
        try:
            self.aur_deps_relations = find_aur_deps(all_aur_packages_names)
        except DependencyVersionMismatch as exc:
            if exc.location is not PackageSource.LOCAL:
                raise exc
            # if local package is too old
            # let's see if a newer one can be found in AUR:
            pkg_name = exc.depends_on
            _aur_pkg_list, not_found_aur_pkgs = find_aur_packages([pkg_name, ])
            if not_found_aur_pkgs:
                raise exc
            # start over computing deps and include just found AUR package:
            self.install_package_names.append(pkg_name)
            self.get_all_packages_info()
            return
        # prepare install info (PackageUpdate objects)
        # for all the AUR packages which gonna be built:
        self.aur_deps_install_info = []
        aur_pkgs = {
            aur_pkg.name: aur_pkg
            for aur_pkg in find_aur_packages(self.aur_deps_names)[0]
        }
        local_pkgs = PackageDB.get_local_dict()
        for pkg_name in self.aur_deps_names:
            aur_pkg = aur_pkgs[pkg_name]
            local_pkg = local_pkgs.get(pkg_name)
            self.aur_deps_install_info.append(PackageUpdate(
                Name=pkg_name,
                Current_Version=local_pkg.version if local_pkg else ' ',
                New_Version=aur_pkg.version,
                Description=aur_pkg.desc
            ))

    def manual_package_selection(self):
        text = pretty_format_sysupgrade(
            self.repo_packages_install_info,
            self.thirdparty_repo_packages_install_info,
            self.aur_updates_install_info,
            color=False
        )
        selected_packages = []
        with NamedTemporaryFile() as tmp_file:
            with open_file(tmp_file.name, 'w') as write_file:
                write_file.write(text)
            interactive_spawn(
                self.get_editor() + [tmp_file.name, ]
            )
            with open_file(tmp_file.name, 'r') as read_file:
                for line in read_file.readlines():
                    line = line.lstrip()
                    if not line:
                        continue
                    if not line.startswith('::') and not line.startswith('#'):
                        pkg_name = line.split()[0]
                        if '/' in pkg_name:
                            pkg_name = pkg_name.split('/')[1]
                        selected_packages.append(pkg_name)
        for pkg_update in (
                self.repo_packages_install_info +
                self.thirdparty_repo_packages_install_info +
                self.aur_updates_install_info
        ):
            pkg_name = pkg_update.Name
            if pkg_name not in selected_packages:
                self.manually_excluded_packages_names.append(pkg_name)
                if pkg_name in self.install_package_names:
                    self.install_package_names.remove(pkg_name)

    def install_prompt(self) -> None:

        def _print_sysupgrade(verbose=False) -> None:
            print(pretty_format_sysupgrade(
                self.repo_packages_install_info,
                self.thirdparty_repo_packages_install_info,
                self.aur_updates_install_info,
                self.aur_deps_install_info,
                verbose=verbose
            ))

        def _confirm_sysupgrade(verbose=False) -> str:
            _print_sysupgrade(verbose=verbose)
            prompt = '{} {}\n{} {}\n>> '.format(
                color_line('::', 12),
                bold_line(_('Proceed with installation? [Y/n] ')),
                color_line('::', 12),
                bold_line(_('[v]iew package detail   [m]anually select packages')))

            answer = get_input(prompt, 'Ynvm')

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
                    self.manual_package_selection()
                    self.get_all_packages_info()
                    self.install_prompt()
                    break
                else:
                    sys.exit(125)
            else:
                break

    def discard_aur_package(
            self, canceled_pkg_name: str, already_discarded: List[str] = None
    ) -> None:
        if canceled_pkg_name in self.install_package_names:
            self.install_package_names.remove(canceled_pkg_name)
        already_discarded = (already_discarded or []) + [canceled_pkg_name]
        packages_to_be_removed = []
        for aur_pkg_name, aur_deps in list(self.aur_deps_relations.items())[:]:
            if canceled_pkg_name in aur_deps + [aur_pkg_name]:
                for pkg_name in aur_deps + [aur_pkg_name]:
                    if pkg_name not in already_discarded:
                        self.discard_aur_package(pkg_name, already_discarded)
                    pkg_build = self.package_builds_by_name.get(pkg_name)
                    if pkg_build and pkg_build.built_packages_installed and \
                       pkg_build.built_packages_installed.get(pkg_name):
                        packages_to_be_removed.append(pkg_name)
                if aur_pkg_name in self.aur_deps_relations:
                    del self.aur_deps_relations[aur_pkg_name]
        if packages_to_be_removed:
            self._remove_packages(list(set(packages_to_be_removed)))

    def get_package_builds(self) -> None:
        if not self.all_aur_packages_names:
            self.package_builds_by_name = {}
            return
        while self.all_aur_packages_names:
            try:
                self.package_builds_by_name = \
                    clone_aur_repos(self.all_aur_packages_names)
                break
            except CloneError as err:
                package_build = err.build
                print_status_message(color_line(
                    (
                        _("Can't clone '{name}' in '{path}' from AUR:")
                        if package_build.clone else
                        _("Can't pull '{name}' in '{path}' from AUR:")
                    ).format(
                        name=', '.join(package_build.package_names),
                        path=package_build.repo_path
                    ),
                    9
                ))
                print_status_message(err.result.stdout_text)
                print_status_message(err.result.stderr_text)
                if self.args.noconfirm:
                    answer = _("a")
                else:
                    prompt = '{} {}\n{}\n{}\n{}\n{}\n> '.format(
                        color_line('::', 11),
                        _("Try recovering?"),
                        _("[c] git checkout -- '*'"),
                        # _("[c] git checkout -- '*' ; git clean -f -d -x"),
                        _("[r] remove dir and clone again"),
                        _("[s] skip this package"),
                        _("[a] abort"))

                    answer = get_input(prompt, 'crsA')

                answer = answer.lower()[0]
                if answer == _("c"):
                    package_build.git_reset_changed()
                elif answer == _("r"):
                    remove_dir(package_build.repo_path)
                elif answer == _("s"):
                    for skip_pkg_name in package_build.package_names:
                        self.discard_aur_package(skip_pkg_name)
                else:
                    sys.exit(125)

    def ask_to_continue(self, text: str = None, default_yes=True) -> bool:
        return ask_to_continue(text=text, default_yes=default_yes, args=self.args)

    def ask_about_package_conflicts(self) -> None:
        print(_('looking for conflicting packages...'))
        conflict_result = find_conflicts(
            list(self.repo_packages_by_name.values()), self.aur_packages_names
        )
        if not conflict_result:
            return
        all_new_packages_names = list(self.repo_packages_by_name.keys()) + self.aur_packages_names
        for new_pkg_name, new_pkg_conflicts in conflict_result.items():
            for pkg_conflict in new_pkg_conflicts:
                if pkg_conflict in all_new_packages_names:
                    print_status_message(color_line(
                        _("New packages '{new}' and '{other}' are in conflict.").format(
                            new=new_pkg_name, other=pkg_conflict),
                        9))
                    sys.exit(131)
        for new_pkg_name, new_pkg_conflicts in conflict_result.items():
            if new_pkg_name in self.repo_packages_by_name:
                continue
            for pkg_conflict in new_pkg_conflicts:
                print_status_message('{} {}'.format(
                    color_line(_("warning:"), 11),
                    _("New package '{new}' conflicts with installed '{installed}'.").format(
                        new=new_pkg_name, installed=pkg_conflict)
                ))
                answer = self.ask_to_continue('{} {}'.format(
                    color_line('::', 11),
                    _("Do you want to remove '{installed}'?").format(installed=pkg_conflict)
                ), default_yes=False)
                if not answer:
                    sys.exit(125)

    def ask_to_edit_file(self, filename: str, package_build: PackageBuild) -> bool:
        noedit = self.args.noedit or PikaurConfig().build.get('NoEdit')
        if noedit or self.args.noconfirm:
            print_status_message('{} {}'.format(
                color_line('::', 11),
                _("Skipping review of {file} for {name} package ({flag})").format(
                    file=filename,
                    name=', '.join(package_build.package_names),
                    flag=(noedit and '--noedit') or
                    (self.args.noconfirm and '--noconfirm')),
            ))
            return False
        if self.ask_to_continue(
                _("Do you want to {edit} {file} for {name} package?").format(
                    edit=bold_line(_("edit")),
                    file=filename,
                    name=bold_line(', '.join(package_build.package_names)),
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
        for repo_status in self.package_builds_by_name.values():
            if repo_status.reviewed:
                continue
            if self.args.needed and repo_status.version_already_installed:
                for package_name in repo_status.package_names:
                    print_package_uptodate(package_name, PackageSource.AUR)
                    self.discard_aur_package(package_name)
                continue
            if repo_status.build_files_updated and not self.args.noconfirm:
                if self.ask_to_continue(
                        _("Do you want to see build files {diff} for {name} package?").format(
                            diff=bold_line(_("diff")),
                            name=bold_line(', '.join(repo_status.package_names))
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
            src_info = SrcInfo(repo_status.repo_path)

            if self.get_editor():
                if self.ask_to_edit_file('PKGBUILD', repo_status):
                    src_info.regenerate()
                    # @TODO: recompute AUR deps
                for pkg_name in repo_status.package_names:
                    install_src_info = SrcInfo(repo_status.repo_path, pkg_name)
                    install_file_name = install_src_info.get_install_script()
                    if install_file_name:
                        self.ask_to_edit_file(install_file_name, repo_status)

            arch = platform.machine()
            supported_archs = src_info.get_values('arch')
            if supported_archs and (
                    'any' not in supported_archs
            ) and (
                arch not in supported_archs
            ):
                print_status_message("{} {}".format(
                    color_line(':: error:', 9),
                    _("{name} can't be built on the current arch ({arch}). "
                      "Supported: {suparch}").format(
                          name=bold_line(', '.join(repo_status.package_names)),
                          arch=arch,
                          suparch=', '.join(supported_archs))
                ))
                sys.exit(95)
            repo_status.reviewed = True

    def build_packages(self) -> None:
        failed_to_build_package_names = []
        deps_fails_counter: Dict[str, int] = {}
        packages_to_be_built = self.all_aur_packages_names[:]
        index = 0
        while packages_to_be_built:
            if index >= len(packages_to_be_built):
                index = 0

            pkg_name = packages_to_be_built[index]
            repo_status = self.package_builds_by_name[pkg_name]
            if self.args.needed and repo_status.version_already_installed:
                packages_to_be_built.remove(pkg_name)
                print_package_uptodate(pkg_name, PackageSource.AUR)
                continue

            try:
                repo_status.build(self.package_builds_by_name)
            except (BuildError, DependencyError) as exc:
                print_status_message(exc)
                print_status_message(
                    color_line(_("Can't build '{name}'.").format(name=pkg_name), 9)
                )
                # if not self.ask_to_continue():
                #     sys.exit(125)
                for _pkg_name in repo_status.package_names:
                    failed_to_build_package_names.append(_pkg_name)
                    self.discard_aur_package(_pkg_name)
                    for remaining_aur_pkg_name in packages_to_be_built[:]:
                        if remaining_aur_pkg_name not in self.all_aur_packages_names:
                            packages_to_be_built.remove(remaining_aur_pkg_name)
            except DependencyNotBuiltYet:
                index += 1
                for _pkg_name in repo_status.package_names:
                    deps_fails_counter.setdefault(_pkg_name, 0)
                    deps_fails_counter[_pkg_name] += 1
                    if deps_fails_counter[_pkg_name] > len(self.all_aur_packages_names):
                        print_status_message('{} {}'.format(
                            color_line(":: " + _("error:"), 9),
                            _("Dependency cycle detected between {}").format(deps_fails_counter)
                        ))
                        sys.exit(131)
            else:
                for _pkg_name in repo_status.package_names:
                    packages_to_be_built.remove(_pkg_name)

        self.failed_to_build_package_names = failed_to_build_package_names

    def _remove_packages(self, packages_to_be_removed: List[str]) -> None:
        # pylint: disable=no-self-use
        if packages_to_be_removed:
            retry_interactive_command_or_exit(
                [
                    'sudo',
                ] + get_pacman_command(self.args) + [
                    '-Rs',
                ] + packages_to_be_removed,
                args=self.args
            )

    def _install_repo_packages(self, packages_to_be_installed: List[str]) -> None:
        if list(self.repo_packages_by_name.keys()) or self.args.sysupgrade:
            extra_args = []
            for excluded_pkg_name in self.manually_excluded_packages_names:
                extra_args.append('--ignore')
                extra_args.append(excluded_pkg_name)
            if not retry_interactive_command(
                    [
                        'sudo',
                    ] + get_pacman_command(self.args) + [
                        '--sync',
                    ] + reconstruct_args(self.args, ignore_args=[
                        'sync',
                        'refresh',
                        'ignore',
                    ]) + packages_to_be_installed + extra_args,
                    args=self.args
            ):
                if not self.ask_to_continue(default_yes=False):
                    self.revert_repo_transaction()
                    sys.exit(125)

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
        print_status_message('{} {}'.format(
            color_line(':: warning', 9),
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
        repo_packages = list(self.repo_packages_by_name.keys())
        self._install_repo_packages(repo_packages)
        self.save_repo_transaction(repo_packages)

    def install_new_aur_deps(self) -> None:
        new_aur_deps_to_install = [
            self.package_builds_by_name[pkg_name].built_packages_paths[pkg_name]
            for pkg_name in self.aur_deps_names
            if self.package_builds_by_name[pkg_name].built_packages_paths.get(pkg_name) and
            not self.package_builds_by_name[pkg_name].built_packages_installed.get(pkg_name)
        ]
        if new_aur_deps_to_install:
            if not retry_interactive_command(
                    [
                        'sudo',
                    ] + get_pacman_command(self.args) + [
                        '--upgrade',
                        '--asdeps',
                    ] + reconstruct_args(self.args, ignore_args=[
                        'upgrade',
                        'asdeps',
                        'sync',
                        'sysupgrade',
                        'refresh',
                        'ignore',
                    ]) + new_aur_deps_to_install,
                    args=self.args
            ):
                if not self.ask_to_continue(default_yes=False):
                    self.revert_aur_transaction()
                    sys.exit(125)
            self.save_aur_transaction(new_aur_deps_to_install)

    def install_aur_packages(self) -> None:
        aur_packages_to_install = [
            self.package_builds_by_name[pkg_name].built_packages_paths[pkg_name]
            for pkg_name in self.aur_packages_names
            if self.package_builds_by_name[pkg_name].built_packages_paths.get(pkg_name) and
            not self.package_builds_by_name[pkg_name].built_packages_installed.get(pkg_name)
        ]
        if aur_packages_to_install:
            if not retry_interactive_command(
                    [
                        'sudo',
                    ] + get_pacman_command(self.args) + [
                        '--upgrade',
                    ] + reconstruct_args(self.args, ignore_args=[
                        'upgrade',
                        'sync',
                        'sysupgrade',
                        'refresh',
                        'ignore',
                    ]) + aur_packages_to_install,
                    args=self.args
            ):
                if not self.ask_to_continue(default_yes=False):
                    self.revert_aur_transaction()
                    sys.exit(125)
            self.save_aur_transaction(aur_packages_to_install)
