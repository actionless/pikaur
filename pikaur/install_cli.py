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


def install_prompt(repo_packages_names, aur_packages_names, aur_deps_names):
    repo_pkgs = PackageDB.get_repo_dict()
    local_pkgs = PackageDB.get_local_dict()
    aur_pkgs = {
        aur_pkg['Name']: aur_pkg
        for aur_pkg in find_aur_packages(aur_packages_names+aur_deps_names)[0]
    }

    repo_packages_updates = []
    for pkg_name in repo_packages_names:
        repo_pkg = repo_pkgs[pkg_name]
        local_pkg = local_pkgs.get(pkg_name)
        repo_packages_updates.append(PackageUpdate(
            Name=pkg_name,
            Current_Version=local_pkg.Version if local_pkg else ' ',
            New_Version=repo_pkg.Version,
            Description=repo_pkg.Description
        ))

    aur_updates = []
    for pkg_name in aur_packages_names:
        aur_pkg = aur_pkgs[pkg_name]
        local_pkg = local_pkgs.get(pkg_name)
        aur_updates.append(PackageUpdate(
            Name=pkg_name,
            Current_Version=local_pkg.Version if local_pkg else ' ',
            New_Version=aur_pkg['Version'],
            Description=aur_pkg['Description']
        ))

    aur_deps = []
    for pkg_name in aur_deps_names:
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
    return answer


def get_package_builds(all_aur_packages_names):
    if not all_aur_packages_names:
        return []
    try:
        return clone_pkgbuilds_git_repos(all_aur_packages_names)
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


def ask_about_package_conflicts(repo_packages_names, aur_packages_names):
    conflict_result = check_conflicts(repo_packages_names, aur_packages_names)
    if not conflict_result:
        return []
    all_new_packages_names = repo_packages_names + aur_packages_names
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
            # packages_to_be_removed.append
    return list(set(reduce(
        lambda x, y: x+y,
        conflict_result.values(),
        []
    )))


def review_build_files(all_aur_packages_names, package_builds, args):
    for pkg_name in reversed(all_aur_packages_names):
        repo_status = package_builds[pkg_name]
        if args.needed and repo_status.version_already_installed:
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


def build_packages(all_aur_packages_names, package_builds, args):
    failed_to_build = []
    for pkg_name in reversed(all_aur_packages_names):
        repo_status = package_builds[pkg_name]
        if args.needed and repo_status.already_installed:
            continue
        try:
            repo_status.build(args, package_builds)
        except BuildError:
            print(color_line(f"Can't build '{pkg_name}'.", 9))
            failed_to_build.append(pkg_name)
            # if not ask_to_continue():
            #     sys.exit(1)
    return failed_to_build


def remove_conflicting_packages(packages_to_be_removed):
    if packages_to_be_removed:
        if not retry_interactive_command(
                [
                    'sudo',
                    'pacman',
                    # '-Rs',  # @TODO: manually remove dependencies of conflicting packages,
                    # but excluding already built AUR packages from that list.
                    '-R',
                    '--noconfirm',
                ] + packages_to_be_removed,
        ):
            if not ask_to_continue(default_yes=False):
                sys.exit(1)


def install_repo_packages(repo_packages_names, args):
    if repo_packages_names:
        if not retry_interactive_command(
                [
                    'sudo',
                    'pacman',
                    '--sync',
                    '--noconfirm',
                ] + reconstruct_args(args, ignore_args=[
                    'sync',
                    'noconfirm',
                    'sysupgrade',
                    'refresh',
                ]) + repo_packages_names,
        ):
            if not ask_to_continue(default_yes=False):
                sys.exit(1)


def install_new_aur_deps(aur_deps_names, package_builds, args):
    new_aur_deps_to_install = [
        package_builds[pkg_name].built_package_path
        for pkg_name in aur_deps_names
        if package_builds[pkg_name].built_package_path
    ]
    if new_aur_deps_to_install:
        if not retry_interactive_command(
                [
                    'sudo',
                    'pacman',
                    '--upgrade',
                    '--asdeps',
                    '--noconfirm',
                ] + reconstruct_args(args, ignore_args=[
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


def install_aur_packages(aur_packages_names, package_builds, args):
    aur_packages_to_install = [
        package_builds[pkg_name].built_package_path
        for pkg_name in aur_packages_names
        if package_builds[pkg_name].built_package_path
    ]
    if aur_packages_to_install:
        if not retry_interactive_command(
                [
                    'sudo',
                    'pacman',
                    '--upgrade',
                    '--noconfirm',
                ] + reconstruct_args(args, ignore_args=[
                    'upgrade',
                    'noconfirm',
                    'sync',
                    'sysupgrade',
                    'refresh',
                ]) + aur_packages_to_install,
        ):
            if not ask_to_continue(default_yes=False):
                sys.exit(1)


def cli_install_packages(args, packages=None):
    packages = packages or args.positional
    if args.ignore:
        for ignored_pkg in args.ignore:
            if ignored_pkg in packages:
                packages.remove(ignored_pkg)

    print("resolving dependencies...")
    repo_packages_names, aur_packages_names = find_repo_packages(packages)
    aur_deps_names = find_aur_deps(aur_packages_names)

    if not args.noconfirm:
        install_prompt(
            repo_packages_names, aur_packages_names, aur_deps_names
        )

    all_aur_packages_names = aur_packages_names + aur_deps_names
    package_builds = get_package_builds(all_aur_packages_names)
    # @TODO: ask to install optdepends (?)
    packages_to_be_removed = ask_about_package_conflicts(
        repo_packages_names, all_aur_packages_names
    )
    review_build_files(
        all_aur_packages_names, package_builds, args
    )

    # get sudo for further questions:
    interactive_spawn(['sudo', 'true'])

    failed_to_build = build_packages(
        all_aur_packages_names, package_builds, args
    )

    remove_conflicting_packages(packages_to_be_removed)
    install_repo_packages(repo_packages_names, args)
    if args.downloadonly:
        return
    install_new_aur_deps(
        aur_deps_names, package_builds, args
    )
    install_aur_packages(
        aur_packages_names, package_builds, args
    )

    # save git hash of last sucessfully installed package
    if package_builds:
        for repo_status in package_builds.values():
            if repo_status.built_package_path:
                repo_status.update_last_installed_file()

    if failed_to_build:
        print('\n'.join(
            [color_line(f"Failed to build following packages:", 9), ] +
            failed_to_build
        ))
