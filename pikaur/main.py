#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
# import argparse
import readline
import shutil
from functools import reduce

from .args import parse_args, reconstruct_args
from .core import (
    SingleTaskExecutor, MultipleTasksExecutor,
    CmdTaskWorker, interactive_spawn,
    ask_to_continue, retry_interactive_command,
)
from .pprint import (
    color_line, bold_line, format_paragraph,
    print_not_found_packages,
    print_upgradeable, pretty_print_upgradeable,
    print_version, print_sysupgrade,
)
from .aur import (
    AurTaskWorkerSearch, AurTaskWorkerInfo,
)
from .pacman import (
    PacmanColorTaskWorker, PackageDB,
    find_repo_packages, find_packages_not_from_repo,
)
from .meta_package import (
    find_repo_updates, find_aur_updates, find_aur_deps, check_conflicts,
)
from .build import SrcInfo, BuildError, CloneError, clone_pkgbuilds_git_repos


def init_readline():
    # follow GNU readline config in prompts:
    system_inputrc_path = '/etc/inputrc'
    if os.path.exists(system_inputrc_path):
        readline.read_init_file(system_inputrc_path)
    user_inputrc_path = os.path.expanduser('~/.inputrc')
    if os.path.exists(user_inputrc_path):
        readline.read_init_file(user_inputrc_path)


init_readline()


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


def cli_install_packages(args, noconfirm=None, packages=None):
    # @TODO: split into smaller routines
    if noconfirm is None:
        noconfirm = args.noconfirm
    print("resolving dependencies...")
    packages = packages or args.positional
    if args.ignore:
        for ignored_pkg in args.ignore:
            if ignored_pkg in packages:
                packages.remove(ignored_pkg)
    repo_packages_names, aur_packages_names = find_repo_packages(packages)
    aur_deps_names = find_aur_deps(aur_packages_names)

    failed_to_build = []

    # confirm package install/upgrade
    if not noconfirm:
        print()
        if repo_packages_names:
            print(color_line("New packages will be installed:", 12))
            print(format_paragraph(' '.join(repo_packages_names)))
        if aur_packages_names:
            print(color_line("New packages will be installed from AUR:", 14))
            print(format_paragraph(' '.join(aur_packages_names)))
        if aur_deps_names:
            print(color_line(
                "New dependencies will be installed from AUR:", 11
            ))
            print(format_paragraph(' '.join(aur_deps_names)))
        print()

        answer = input('{} {}'.format(
            color_line('::', 12),
            bold_line('Proceed with installation? [Y/n] '),
        ))
        if answer:
            if answer.lower()[0] != 'y':
                sys.exit(1)

    all_aur_packages_names = aur_packages_names + aur_deps_names
    package_builds = None
    if all_aur_packages_names:
        try:
            package_builds = clone_pkgbuilds_git_repos(all_aur_packages_names)
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

    # @TODO: ask to install optdepends (?)

    # ask about package conflicts
    packages_to_be_removed = []
    conflict_result = check_conflicts(repo_packages_names, aur_packages_names)
    if conflict_result:
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
        packages_to_be_removed = list(set(reduce(
            lambda x, y: x+y,
            conflict_result.values(),
            []
        )))

    # review PKGBUILD and install files
    for pkg_name in reversed(all_aur_packages_names):
        repo_status = package_builds[pkg_name]
        repo_path = repo_status.repo_path
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
            if get_editor():
                ask_to_edit_file('PKGBUILD', repo_status)
                install_file_name = SrcInfo(repo_path).get_install_script()
                if install_file_name:
                    ask_to_edit_file(install_file_name, repo_status)

    # get sudo for further questions:
    interactive_spawn([
        'sudo', 'true'
    ])

    # build packages:
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

    # remove conflicting packages:
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

    # install packages:

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

    if args.downloadonly:
        return

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

    # save git hash of last sucessfully installed package
    if package_builds:
        for pkg_name, repo_status in package_builds.items():
            if repo_status.built_package_path:
                shutil.copy2(
                    os.path.join(
                        repo_status.repo_path,
                        '.git/refs/heads/master'
                    ),
                    repo_status.last_installed_file_path
                )

    if failed_to_build:
        print('\n'.join(
            [color_line(f"Failed to build following packages:", 9), ] +
            failed_to_build
        ))


def cli_print_upgradeable(args):
    updates, _ = find_aur_updates(find_packages_not_from_repo())
    updates += find_repo_updates()
    updates = sorted(updates, key=lambda u: u.Name)
    if args.quiet:
        print_upgradeable(updates)
    else:
        pretty_print_upgradeable(updates)


def cli_upgrade_packages(args):
    if args.refresh:
        interactive_spawn(['sudo', 'pacman', '--sync', '--refresh'])
    ignore = args.ignore or []

    print('{} {}'.format(
        color_line('::', 12),
        bold_line('Starting full system upgrade...')
    ))
    repo_packages_updates = [
        pkg for pkg in find_repo_updates()
        if pkg.Name not in ignore
    ]

    print('{} {}'.format(
        color_line('::', 12),
        bold_line('Starting full AUR upgrade...')
    ))
    aur_updates, not_found_aur_pkgs = \
        find_aur_updates(find_packages_not_from_repo())
    print_not_found_packages(sorted(not_found_aur_pkgs))
    aur_updates = [
        pkg for pkg in aur_updates
        if pkg.Name not in ignore
    ]

    all_upgradeable_package_names = [
        u.Name for u in repo_packages_updates
    ] + [
        u.Name for u in aur_updates
    ]
    if not all_upgradeable_package_names:
        print('\n{} {}'.format(
            color_line('::', 10),
            bold_line('Already up-to-date.')
        ))
        return

    answer = None
    while True:
        if answer is None:
            answer = print_sysupgrade(repo_packages_updates, aur_updates)
        if answer:
            letter = answer.lower()[0]
            if letter == 'y':
                break
            elif letter == 'v':
                answer = print_sysupgrade(
                    repo_packages_updates, aur_updates, verbose=True
                )
            elif letter == 'm':
                # @TODO: implement [m]anual package selection
                raise NotImplementedError()
            else:
                sys.exit(1)
        else:
            break

    cli_install_packages(
        args=args,
        packages=all_upgradeable_package_names,
        noconfirm=True
    )


def cli_info_packages(args):
    pkgs = 'pkgs'
    aur = 'aur'
    result = MultipleTasksExecutor({
        pkgs: PacmanColorTaskWorker(args.raw),
        aur: AurTaskWorkerInfo(
            packages=args.positional or []
        ),
    }).execute()
    json_results = result[aur].json['results']
    num_found = len(json_results)
    if result[pkgs].stdout:
        print(result[pkgs].stdout, end='\n' if json_results else '')
    for i, result in enumerate(json_results):
        print(
            '\n'.join([
                '{key:24}: {value}'.format(
                    key=bold_line(key),
                    value=value if not isinstance(value, list)
                    else ', '.join(value)
                )
                for key, value in result.items()
            ]) + ('\n' if i+1 < num_found else '')
        )


def cli_clean_packages_cache(_args):
    print(_args)
    # @TODO: implement -Sc and -Scc
    raise NotImplementedError()


def cli_search_packages(args):

    class GetLocalPkgsVersionsTask():
        async def get_task(self):
            return {
                pkg_name: pkg.Version
                for pkg_name, pkg in PackageDB.get_local_dict().items()
            }

    repo = 'repo'
    aur = 'aur'
    local = 'local'
    result = MultipleTasksExecutor({
        repo: PacmanColorTaskWorker(args.raw),
        aur: AurTaskWorkerSearch(
            search_query=' '.join(args.positional or [])
        ),
        local: GetLocalPkgsVersionsTask,
    }).execute()
    local_pkgs_versions = result[local]
    local_pkgs_names = local_pkgs_versions.keys()

    if result[repo].stdout != '':
        print(result[repo].stdout)
    for aur_pkg in result[aur].json['results']:
        pkg_name = aur_pkg['Name']
        if args.quiet:
            print(pkg_name)
        else:
            print("{}{} {} {}".format(
                # color_line('aur/', 13),
                color_line('aur/', 9),
                bold_line(pkg_name),
                color_line(aur_pkg["Version"], 10),
                color_line('[installed{}]'.format(
                    f': {local_pkgs_versions[pkg_name]}'
                    if aur_pkg['Version'] != local_pkgs_versions[pkg_name]
                    else ''
                ), 14)
                if pkg_name in local_pkgs_names else '',
            ))
            print(format_paragraph(f'{aur_pkg["Description"]}'))


def main():
    # pylint: disable=too-many-branches
    raw_args = sys.argv[1:]
    args = parse_args(raw_args)

    not_implemented_in_pikaur = False
    require_sudo = True

    if args.sync:
        if args.sysupgrade:
            cli_upgrade_packages(args)
        elif args.search:
            cli_search_packages(args)
        elif args.info:
            cli_info_packages(args)
        elif args.clean:
            cli_clean_packages_cache(args)
        elif '-S' in raw_args or '--sync' in raw_args:
            cli_install_packages(args)
        elif args.groups:
            not_implemented_in_pikaur = True
            require_sudo = False
        else:
            not_implemented_in_pikaur = True

    elif args.query:
        if args.sysupgrade:
            cli_print_upgradeable(args)
        else:
            not_implemented_in_pikaur = True
            require_sudo = False

    elif args.version:
        print_version()
    else:
        not_implemented_in_pikaur = True

    if args.help:
        require_sudo = False

    if not_implemented_in_pikaur:
        if require_sudo:
            sys.exit(
                interactive_spawn(['sudo', 'pacman', ] + raw_args).returncode
            )
        sys.exit(
            interactive_spawn(['pacman', ] + raw_args).returncode
        )


if __name__ == '__main__':
    if os.getuid() == 0:
        print("{} {}".format(
            color_line('::', 9),
            "Don't run me as root."
        ))
        sys.exit(1)
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
