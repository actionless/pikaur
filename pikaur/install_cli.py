import platform
import sys
import os
from tempfile import NamedTemporaryFile
from functools import reduce

from .args import reconstruct_args
from .aur import find_aur_packages
from .aur_deps import find_aur_deps
from .pacman import (
    find_repo_packages, PackageDB, OFFICIAL_REPOS, PacmanConfig,
)
from .package_update import PackageUpdate, get_remote_package_version
from .exceptions import (
    PackagesNotFoundInAUR, DependencyVersionMismatch,
    BuildError, CloneError, DependencyError, DependencyNotBuiltYet,
)
from .build import (
    SrcInfo,
    clone_pkgbuilds_git_repos,
)
from .pprint import (
    color_line, bold_line,
    pretty_format_sysupgrade, pretty_format_upgradeable,
    print_not_found_packages,
)
from .core import (
    SingleTaskExecutor, CmdTaskWorker,
    interactive_spawn, remove_dir,
)
from .conflicts import (
    check_conflicts, check_replacements,
)
from .prompt import (
    ask_to_continue, retry_interactive_command,
    retry_interactive_command_or_exit,
)


def get_editor():
    editor = os.environ.get('VISUAL') or os.environ.get('EDITOR')
    if editor:
        return editor
    for editor in ('vim', 'nano', 'mcedit', 'edit'):
        result = SingleTaskExecutor(
            CmdTaskWorker(['which', editor])
        ).execute()
        if result.return_code == 0:
            return editor
    print(
        '{} {}'.format(
            color_line('error:', 9),
            'no editor found. Try setting $VISUAL or $EDITOR.'
        )
    )
    if not ask_to_continue('Do you want to proceed without editing?'):
        sys.exit(2)
    return None


def exclude_ignored_packages(package_names, args):
    excluded_pkgs = []
    for ignored_pkg in (args.ignore or []) + PacmanConfig.get('IgnorePkg', []):
        if ignored_pkg in package_names:
            package_names.remove(ignored_pkg)
            excluded_pkgs.append(ignored_pkg)
    return excluded_pkgs


def manual_package_selection(text):
    selected_packages = []
    with NamedTemporaryFile() as tmp_file:
        with open(tmp_file.name, 'w') as write_file:
            write_file.write(text)
        interactive_spawn([
            get_editor(),
            tmp_file.name
        ])
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


class InstallPackagesCLI():

    args = None
    repo_packages_names = None
    aur_packages_names = None
    aur_deps_names = None
    package_builds = None
    aur_packages_conflicts = None
    repo_packages_conflicts = None
    failed_to_build = None
    transactions = None
    REPO = 'repo'
    AUR = 'aur'

    def __init__(self, args, packages=None):
        self.args = args

        packages = packages or args.positional
        self.exclude_ignored_packages(packages)
        if not packages:
            print('{} {}'.format(
                color_line('::', 10),
                "Nothing to do."
            ))
            return
        self.find_packages(packages)

        self.install_prompt()

        self.get_package_builds()
        # @TODO: ask to install optdepends (?)
        if not args.downloadonly:
            self.ask_about_package_conflicts()
            self.ask_about_package_replacements()
        self.review_build_files()

        # get sudo for further questions (command should do nothing):
        interactive_spawn(['sudo', 'pacman', '-T'])

        self.build_packages()

        self.remove_repo_packages_conflicts()
        self.install_repo_packages()
        if not args.downloadonly:
            self.remove_aur_packages_conflicts()
            self.install_new_aur_deps()
            self.install_aur_packages()

        # save git hash of last sucessfully installed package
        if self.package_builds:
            for package_build in self.package_builds.values():
                if package_build.built_package_path:
                    package_build.update_last_installed_file()
                    remove_dir(package_build.build_dir)

        if self.failed_to_build:
            print('\n'.join(
                [color_line(f"Failed to build following packages:", 9), ] +
                self.failed_to_build
            ))

    @property
    def all_aur_packages_names(self):
        return self.aur_packages_names + self.aur_deps_names

    def exclude_ignored_packages(self, packages):
        excluded_packages = exclude_ignored_packages(packages, self.args)
        for package_name in excluded_packages:
            current = PackageDB.get_local_dict().get(package_name)
            current_version = current.Version if current else ''
            new_version = get_remote_package_version(package_name)
            print('{} Ignoring package {}'.format(
                color_line('::', 11),
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
                )
            ))

    def find_packages(self, packages):
        print("resolving dependencies...")
        self.repo_packages_names, self.aur_packages_names = find_repo_packages(
            packages
        )
        try:
            self.aur_deps_names = find_aur_deps(self.aur_packages_names)
        except PackagesNotFoundInAUR as exc:
            if exc.wanted_by:
                print("{} {}".format(
                    color_line(':: error:', 9),
                    bold_line(
                        'Dependencies missing for '
                        f'{exc.wanted_by}'
                    ),
                ))
            print_not_found_packages(exc.packages)
            sys.exit(1)
        except DependencyVersionMismatch as exc:
            print("{}\n {} depends on: '{}'\n found in '{}': '{}'".format(
                color_line("Version mismatch:", 11),
                bold_line(exc.who_depends),
                exc.dependency_line,
                exc.location,
                exc.version_found
            ))
            sys.exit(1)

    def _get_repo_pkgs_updates(self):
        repo_pkgs = PackageDB.get_repo_dict()
        local_pkgs = PackageDB.get_local_dict()
        repo_packages_updates = []
        thirdparty_repo_packages_updates = []
        for pkg_name in self.repo_packages_names:
            repo_pkg = repo_pkgs[pkg_name]
            local_pkg = local_pkgs.get(pkg_name)
            pkg = PackageUpdate(
                Name=pkg_name,
                Current_Version=local_pkg.Version if local_pkg else ' ',
                New_Version=repo_pkg.Version,
                Description=repo_pkg.Description,
                Repository=repo_pkg.Repository
            )
            if repo_pkg.Repository in OFFICIAL_REPOS:
                repo_packages_updates.append(pkg)
            else:
                thirdparty_repo_packages_updates.append(pkg)
        return repo_packages_updates, thirdparty_repo_packages_updates

    def _get_aur_updates(self):
        local_pkgs = PackageDB.get_local_dict()
        aur_pkgs = {
            aur_pkg.Name: aur_pkg
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
                Current_Version=local_pkg.Version if local_pkg else ' ',
                New_Version=aur_pkg.Version,
                Description=aur_pkg.Description
            ))
        return aur_updates

    def _get_aur_deps(self):
        local_pkgs = PackageDB.get_local_dict()
        aur_pkgs = {
            aur_pkg.Name: aur_pkg
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
                Current_Version=local_pkg.Version if local_pkg else ' ',
                New_Version=aur_pkg.Version,
                Description=aur_pkg.Description
            ))
        return aur_deps

    def install_prompt(self):
        repo_packages_updates, thirdparty_repo_packages_updates = \
            self._get_repo_pkgs_updates()
        aur_updates = self._get_aur_updates()
        aur_deps = self._get_aur_deps()

        def _print_sysupgrade(verbose=False):
            print(pretty_format_sysupgrade(
                repo_packages_updates, thirdparty_repo_packages_updates,
                aur_updates, aur_deps,
                verbose=verbose
            ))

        def _confirm_sysupgrade(verbose=False):
            _print_sysupgrade(verbose=verbose)
            answer = input('{} {}\n{} {}\n> '.format(
                color_line('::', 12),
                bold_line('Proceed with installation? [Y/n] '),
                color_line('::', 12),
                bold_line('[v]iew package detail   [m]anually select packages')
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
                if letter == 'y':
                    break
                elif letter == 'v':
                    answer = _confirm_sysupgrade(verbose=True)
                elif letter == 'm':
                    print()
                    packages = manual_package_selection(
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

    def get_package_builds(self):
        if not self.all_aur_packages_names:
            self.package_builds = []
            return
        while self.all_aur_packages_names:
            try:
                self.package_builds = clone_pkgbuilds_git_repos(self.all_aur_packages_names)
                break
            except CloneError as err:
                package_build = err.build
                print(color_line(
                    "Can't {} '{}' in '{}' from AUR:".format(
                        'clone' if package_build.clone else 'pull',
                        package_build.package_name,
                        package_build.repo_path
                    ), 9
                ))
                print(err.result)
                if self.args.noconfirm:
                    answer = 'a'
                else:
                    answer = input('{} {}\n{}\n{}\n{}\n{}\n> '.format(
                        color_line('::', 11),
                        'Try recovering?',
                        "[c] git checkout -- '*'",
                        # "[c] git checkout -- '*' ; git clean -f -d -x",
                        '[r] remove dir and clone again',
                        '[s] skip this package',
                        '[a] abort',
                    ))
                answer = answer.lower()[0]
                if answer == 'c':
                    package_build.git_reset_changed()
                elif answer == 'r':
                    remove_dir(package_build.repo_path)
                elif answer == 's':
                    if package_build.package_name in self.aur_packages_names:
                        self.aur_packages_names.remove(package_build.package_name)
                    else:
                        self.aur_deps_names.remove(package_build.package_name)
                else:
                    sys.exit(1)

    def ask_to_continue(self, text=None, default_yes=True):
        return ask_to_continue(text, default_yes, args=self.args)

    def ask_about_package_conflicts(self):
        print('looking for conflicting packages...')
        conflict_result = check_conflicts(
            self.repo_packages_names, self.aur_packages_names
        )
        if not conflict_result:
            self.aur_packages_conflicts = []
            self.repo_packages_conflicts = []
            return
        all_new_packages_names = self.repo_packages_names + self.aur_packages_names
        for new_pkg_name, new_pkg_conflicts in conflict_result.items():
            for pkg_conflict in new_pkg_conflicts:
                if pkg_conflict in all_new_packages_names:
                    print(color_line(
                        f"New packages '{new_pkg_name}' and '{pkg_conflict}' "
                        "are in conflict.",
                        9
                    ))
                    sys.exit(1)
        for new_pkg_name, new_pkg_conflicts in conflict_result.items():
            for pkg_conflict in new_pkg_conflicts:
                print('{} {}'.format(
                    color_line('warning:', 11),
                    f"New package '{new_pkg_name}' conflicts with installed '{pkg_conflict}'.",
                ))
                answer = self.ask_to_continue('{} {}'.format(
                    color_line('::', 11),
                    f"Do you want to remove '{pkg_conflict}'?"
                ), default_yes=False)
                if not answer:
                    sys.exit(1)
        self.aur_packages_conflicts = list(set(reduce(
            lambda x, y: x+y,
            [
                conflicts
                for pkg_name, conflicts in conflict_result.items()
                if pkg_name in self.aur_packages_names
            ],
            []
        )))
        self.repo_packages_conflicts = list(set(reduce(
            lambda x, y: x+y,
            [
                conflicts
                for pkg_name, conflicts in conflict_result.items()
                if pkg_name in self.repo_packages_names
            ],
            []
        )))

    def ask_about_package_replacements(self):
        package_replacements = check_replacements()
        for repo_pkg_name, installed_pkgs_names in package_replacements.items():
            for installed_pkg_name in installed_pkgs_names:
                if self.ask_to_continue(
                        "{} New package '{}' replaces installed '{}'. Proceed?".format(
                            color_line('::', 11),
                            bold_line(repo_pkg_name),
                            bold_line(installed_pkg_name)
                        )
                ):
                    self.repo_packages_names.append(repo_pkg_name)
                    self.repo_packages_conflicts.append(installed_pkg_name)

    def ask_to_edit_file(self, filename, package_build):
        if self.args.noedit or self.args.noconfirm:
            print('{} Skipping review of {} for {} package ({})'.format(
                color_line('::', 11),
                filename,
                package_build.package_name,
                (self.args.noedit and '--noedit') or (self.args.noconfirm and '--noconfirm')
            ))
            return False
        if self.ask_to_continue(
                "Do you want to {} {} for {} package?".format(
                    bold_line('edit'),
                    filename,
                    bold_line(package_build.package_name)
                ),
                default_yes=not package_build.is_installed
        ):
            interactive_spawn([
                get_editor(),
                os.path.join(
                    package_build.repo_path,
                    filename
                )
            ])
            return True
        return False

    def review_build_files(self):
        for pkg_name in self.all_aur_packages_names:
            repo_status = self.package_builds[pkg_name]
            if self.args.needed and repo_status.version_already_installed:
                print(
                    '{} {} {}'.format(
                        color_line('warning:', 11),
                        pkg_name,
                        'is up to date -- skipping'
                    )
                )
            else:

                if repo_status.build_files_updated:
                    if self.ask_to_continue(
                            "Do you want to see build files {} for {} package?".format(
                                bold_line('diff'),
                                bold_line(pkg_name)
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

                if get_editor():
                    if self.ask_to_edit_file('PKGBUILD', repo_status):
                        src_info.regenerate()
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
                    print("{} {} can't be built on the current arch ({}). Supported: {}".format(
                        color_line(':: error:', 9),
                        bold_line(pkg_name),
                        arch,
                        ', '.join(supported_archs)
                    ))
                    sys.exit(1)

    def build_packages(self):
        failed_to_build = []
        deps_fails_counter = {}
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
                print(color_line(f"Can't build '{pkg_name}'.", 9))
                failed_to_build.append(pkg_name)
                # if not self.ask_to_continue():
                #     sys.exit(1)
                packages_to_be_built.remove(pkg_name)
            except DependencyNotBuiltYet:
                index += 1
                deps_fails_counter.setdefault(pkg_name, 0)
                deps_fails_counter[pkg_name] += 1
                if deps_fails_counter[pkg_name] > len(self.all_aur_packages_names):
                    print('{} {} {}'.format(
                        color_line(':: error:', 9),
                        "Dependency cycle detected between",
                        deps_fails_counter
                    ))
                    sys.exit(1)
            else:
                packages_to_be_built.remove(pkg_name)

        self.failed_to_build = failed_to_build

    def _remove_packages(self, packages_to_be_removed):
        # pylint: disable=no-self-use
        if packages_to_be_removed:
            retry_interactive_command_or_exit(
                [
                    'sudo',
                    'pacman',
                    # '-Rs',  # @TODO: manually remove dependencies of conflicting packages,
                    # but excluding already built AUR packages from that list.
                    '-R',
                    '--noconfirm',
                ] + packages_to_be_removed,
            )

    def _install_repo_packages(self, packages_to_be_installed):
        if self.repo_packages_names:
            if not retry_interactive_command(
                    [
                        'sudo',
                        'pacman',
                        '--sync',
                        '--noconfirm',
                    ] + reconstruct_args(self.args, ignore_args=[
                        'sync',
                        'noconfirm',
                        'sysupgrade',
                        'refresh',
                        'ignore',
                    ]) + packages_to_be_installed,
            ):
                if not self.ask_to_continue(default_yes=False):
                    self.revert_repo_transaction()
                    sys.exit(1)

    def _save_transaction(self, target, removed=None, installed=None):
        if not self.transactions:
            self.transactions = {}
        target_transaction = self.transactions.setdefault(target, {})
        if removed:
            for pkg_name in removed:
                target_transaction.setdefault('removed', []).append(pkg_name)
        if installed:
            for pkg_name in installed:
                target_transaction.setdefault('installed', []).append(pkg_name)

    def save_repo_transaction(self, removed=None, installed=None):
        return self._save_transaction(
            self.REPO, removed=removed, installed=installed
        )

    def save_aur_transaction(self, removed=None, installed=None):
        return self._save_transaction(
            self.AUR, removed=removed, installed=installed
        )

    def _revert_transaction(self, target):
        if not self.transactions:
            return
        target_transaction = self.transactions.get(target)
        if not target_transaction:
            return
        print('{} Reverting {} transaction...'.format(
            color_line('::', 9),
            target
        ))
        removed = target_transaction.get('removed')
        installed = target_transaction.get('installed')
        if removed:
            pass  # install back
        if installed:
            self._remove_packages(installed)

    def revert_repo_transaction(self):
        self._revert_transaction(self.REPO)

    def revert_aur_transaction(self):
        self._revert_transaction(self.AUR)

    def _remove_conflicting_packages(self, packages_to_be_removed):
        # pylint: disable=no-self-use
        if packages_to_be_removed:
            retry_interactive_command_or_exit(
                [
                    'sudo',
                    'pacman',
                    # '-Rs',  # @TODO: manually remove dependencies of conflicting packages,
                    # but excluding already built AUR packages from that list.
                    '-R',
                    '--noconfirm',
                    '--nodeps',
                    '--nodeps',
                ] + packages_to_be_removed,
            )

    def remove_repo_packages_conflicts(self):
        self._remove_conflicting_packages(self.repo_packages_conflicts)
        self.save_repo_transaction(removed=self.repo_packages_conflicts)

    def remove_aur_packages_conflicts(self):
        self._remove_conflicting_packages(self.aur_packages_conflicts)
        self.save_aur_transaction(removed=self.aur_packages_conflicts)

    def install_repo_packages(self):
        self._install_repo_packages(self.repo_packages_names)
        self.save_repo_transaction(self.repo_packages_names)

    def install_new_aur_deps(self):
        new_aur_deps_to_install = [
            self.package_builds[pkg_name].built_package_path
            for pkg_name in self.aur_deps_names
            if self.package_builds[pkg_name].built_package_path
        ]
        if new_aur_deps_to_install:
            if not retry_interactive_command(
                    [
                        'sudo',
                        'pacman',
                        '--upgrade',
                        '--asdeps',
                        '--noconfirm',
                    ] + reconstruct_args(self.args, ignore_args=[
                        'upgrade',
                        'asdeps',
                        'noconfirm',
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

    def install_aur_packages(self):
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
                        '--noconfirm',
                    ] + reconstruct_args(self.args, ignore_args=[
                        'upgrade',
                        'noconfirm',
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
