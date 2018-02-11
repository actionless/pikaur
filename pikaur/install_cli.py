import platform
import sys
import os
from functools import reduce

from .args import reconstruct_args
from .aur import find_aur_packages
from .pacman import (
    find_repo_packages, PackageDB,
)
from .meta_package import (
    find_aur_deps, check_conflicts, PackageUpdate,
)
from .build import (
    SrcInfo, BuildError, CloneError, clone_pkgbuilds_git_repos,
    retry_interactive_command,
)
from .pprint import color_line, bold_line, print_sysupgrade
from .core import (
    ask_to_continue, interactive_spawn,
    SingleTaskExecutor, CmdTaskWorker,
)


def get_editor():
    editor = os.environ.get('EDITOR')
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
            'no editor found. Try setting $EDITOR.'
        )
    )
    if not ask_to_continue('Do you want to proceed without editing?'):
        sys.exit(2)
    return None


def ask_to_edit_file(filename, package_build):
    if ask_to_continue(
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


class InstallPackagesCLI():

    args = None
    repo_packages_names = None
    aur_packages_names = None
    aur_deps_names = None
    all_aur_packages_names = None
    package_builds = None
    packages_to_be_removed = None
    failed_to_build = None

    def __init__(self, args, packages=None):
        self.args = args

        packages = packages or args.positional
        if args.ignore:
            for ignored_pkg in args.ignore:
                if ignored_pkg in packages:
                    packages.remove(ignored_pkg)

        print("resolving dependencies...")
        self.repo_packages_names, self.aur_packages_names = find_repo_packages(
            packages
        )
        self.aur_deps_names = find_aur_deps(self.aur_packages_names)
        self.all_aur_packages_names = self.aur_packages_names + self.aur_deps_names

        if not args.noconfirm:
            self.install_prompt()

        self.get_package_builds()
        # @TODO: ask to install optdepends (?)
        if not args.downloadonly:
            self.ask_about_package_conflicts()
        self.review_build_files()

        # get sudo for further questions:
        interactive_spawn(['sudo', 'true'])

        self.build_packages()

        self.remove_conflicting_packages()
        self.install_repo_packages()
        if args.downloadonly:
            return
        self.install_new_aur_deps()
        self.install_aur_packages()

        # save git hash of last sucessfully installed package
        if self.package_builds:
            for package_build in self.package_builds.values():
                if package_build.built_package_path:
                    package_build.update_last_installed_file()

        if self.failed_to_build:
            print('\n'.join(
                [color_line(f"Failed to build following packages:", 9), ] +
                self.failed_to_build
            ))

    def install_prompt(self):
        repo_pkgs = PackageDB.get_repo_dict()
        local_pkgs = PackageDB.get_local_dict()
        aur_pkgs = {
            aur_pkg['Name']: aur_pkg
            for aur_pkg in find_aur_packages(
                self.aur_packages_names+self.aur_deps_names
            )[0]
        }

        repo_packages_updates = []
        for pkg_name in self.repo_packages_names:
            repo_pkg = repo_pkgs[pkg_name]
            local_pkg = local_pkgs.get(pkg_name)
            repo_packages_updates.append(PackageUpdate(
                Name=pkg_name,
                Current_Version=local_pkg.Version if local_pkg else ' ',
                New_Version=repo_pkg.Version,
                Description=repo_pkg.Description
            ))

        aur_updates = []
        for pkg_name in self.aur_packages_names:
            aur_pkg = aur_pkgs[pkg_name]
            local_pkg = local_pkgs.get(pkg_name)
            aur_updates.append(PackageUpdate(
                Name=pkg_name,
                Current_Version=local_pkg.Version if local_pkg else ' ',
                New_Version=aur_pkg['Version'],
                Description=aur_pkg['Description']
            ))

        aur_deps = []
        for pkg_name in self.aur_deps_names:
            aur_pkg = aur_pkgs[pkg_name]
            local_pkg = local_pkgs.get(pkg_name)
            aur_deps.append(PackageUpdate(
                Name=pkg_name,
                Current_Version=local_pkg.Version if local_pkg else ' ',
                New_Version=aur_pkg['Version'],
                Description=aur_pkg['Description']
            ))

        answer = None
        while True:
            if answer is None:
                answer = print_sysupgrade(repo_packages_updates, aur_updates, aur_deps)
            if answer:
                letter = answer.lower()[0]
                if letter == 'y':
                    break
                elif letter == 'v':
                    answer = print_sysupgrade(
                        repo_packages_updates, aur_updates, aur_deps, verbose=True
                    )
                elif letter == 'm':
                    # @TODO: implement [m]anual package selection
                    raise NotImplementedError()
                else:
                    sys.exit(1)
            else:
                break

    def get_package_builds(self):
        if not self.all_aur_packages_names:
            self.package_builds = []
            return
        try:
            self.package_builds = clone_pkgbuilds_git_repos(self.all_aur_packages_names)
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
            if not ask_to_continue():
                sys.exit(1)

    def ask_about_package_conflicts(self):
        conflict_result = check_conflicts(
            self.repo_packages_names, self.aur_packages_names
        )
        if not conflict_result:
            self.packages_to_be_removed = []
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
                answer = ask_to_continue('{} {}'.format(
                    color_line('::', 11),
                    f"Do you want to remove '{pkg_conflict}'?"
                ), default_yes=False)
                if not answer:
                    sys.exit(1)
        self.packages_to_be_removed = list(set(reduce(
            lambda x, y: x+y,
            conflict_result.values(),
            []
        )))

    def review_build_files(self):
        for pkg_name in reversed(self.all_aur_packages_names):
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
                    if ask_to_continue(
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
                src_info = SrcInfo(repo_status.repo_path)

                if get_editor():
                    if ask_to_edit_file('PKGBUILD', repo_status):
                        src_info.regenerate()
                    install_file_name = src_info.get_install_script()
                    if install_file_name:
                        ask_to_edit_file(install_file_name, repo_status)

                arch = platform.machine()
                supported_archs = src_info.get_values('arch')
                if ('any' not in supported_archs) and (arch not in supported_archs):
                    print("{} {} can't be built on the current arch ({}). Supported: {}".format(
                        color_line(':: error:', 9),
                        bold_line(pkg_name),
                        arch,
                        ', '.join(supported_archs)
                    ))
                    sys.exit(1)

    def build_packages(self):
        failed_to_build = []
        for pkg_name in reversed(self.all_aur_packages_names):
            repo_status = self.package_builds[pkg_name]
            if self.args.needed and repo_status.already_installed:
                continue
            try:
                repo_status.build(self.args, self.package_builds)
            except BuildError:
                print(color_line(f"Can't build '{pkg_name}'.", 9))
                failed_to_build.append(pkg_name)
                # if not ask_to_continue():
                #     sys.exit(1)
        self.failed_to_build = failed_to_build

    def remove_conflicting_packages(self):
        if self.packages_to_be_removed:
            if not retry_interactive_command(
                    [
                        'sudo',
                        'pacman',
                        # '-Rs',  # @TODO: manually remove dependencies of conflicting packages,
                        # but excluding already built AUR packages from that list.
                        '-R',
                        '--noconfirm',
                    ] + self.packages_to_be_removed,
            ):
                if not ask_to_continue(default_yes=False):
                    sys.exit(1)

    def install_repo_packages(self):
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
                    ]) + self.repo_packages_names,
            ):
                if not ask_to_continue(default_yes=False):
                    sys.exit(1)

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
                    ]) + new_aur_deps_to_install,
            ):
                if not ask_to_continue(default_yes=False):
                    sys.exit(1)

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
                    ]) + aur_packages_to_install,
            ):
                if not ask_to_continue(default_yes=False):
                    sys.exit(1)
