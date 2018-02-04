#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
# import argparse
import readline
import shutil

from . import argparse as argparse

from .core import (
    SingleTaskExecutor, MultipleTasksExecutor,
    CmdTaskWorker, interactive_spawn,
    get_package_name_from_depend_line,
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
    find_aur_packages,
)
from .pacman import (
    PacmanColorTaskWorker, PackageDB,
    find_repo_packages, find_local_packages,
    find_packages_not_from_repo,
)
from .meta_package import (
    find_repo_updates, find_aur_updates,
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


def find_aur_deps(package_names):

    # @TODO: split to smaller routines

    def _get_deps(result):
        return [
            get_package_name_from_depend_line(dep) for dep in
            result.get('Depends', []) + result.get('MakeDepends', [])
        ]

    new_aur_deps = []
    while package_names:

        all_deps_for_aur_packages = []
        aur_pkgs_info, not_found_aur_pkgs = find_aur_packages(package_names)
        if not_found_aur_pkgs:
            print_not_found_packages(not_found_aur_pkgs)
            sys.exit(1)
        for result in aur_pkgs_info:
            all_deps_for_aur_packages += _get_deps(result)
        all_deps_for_aur_packages = list(set(all_deps_for_aur_packages))

        not_found_local_pkgs = []
        if all_deps_for_aur_packages:
            _, not_found_deps = find_repo_packages(
                all_deps_for_aur_packages
            )

            # pkgs provided by repo pkgs
            if not_found_deps:
                repo_provided = PackageDB.get_repo_provided()
                for dep_name in not_found_deps[:]:
                    if dep_name in repo_provided:
                        not_found_deps.remove(dep_name)

            if not_found_deps:
                _local_pkgs_info, not_found_local_pkgs = \
                    find_local_packages(
                        not_found_deps
                    )

                # pkgs provided by repo pkgs
                if not_found_local_pkgs:
                    local_provided = PackageDB.get_local_provided()
                    for dep_name in not_found_local_pkgs[:]:
                        if dep_name in local_provided:
                            not_found_local_pkgs.remove(dep_name)

                # try finding those packages in AUR
                _aur_deps_info, not_found_aur_deps = find_aur_packages(
                    not_found_local_pkgs
                )
                if not_found_aur_deps:
                    problem_package_names = []
                    for result in aur_pkgs_info:
                        deps = _get_deps(result)
                        for not_found_pkg in not_found_aur_deps:
                            if not_found_pkg in deps:
                                problem_package_names.append(result['Name'])
                                break
                    print("{} {}".format(
                        color_line(':: error:', 9),
                        bold_line(
                            'Dependencies missing for '
                            f'{problem_package_names}'
                        ),
                    ))
                    print_not_found_packages(not_found_aur_deps)
                    sys.exit(1)
        new_aur_deps += not_found_local_pkgs
        package_names = not_found_local_pkgs

    return new_aur_deps


def cli_install_packages(args, noconfirm=None, packages=None):
    # @TODO: split into smaller routines
    if noconfirm is None:
        noconfirm = args.noconfirm
    print("resolving dependencies...")
    packages = packages or args._positional
    if args.ignore:
        for ignored_pkg in args.ignore:
            if ignored_pkg in packages:
                packages.remove(ignored_pkg)
    pacman_packages, aur_packages = find_repo_packages(packages)
    new_aur_deps = find_aur_deps(aur_packages)

    failed_to_build = []

    # confirm package install/upgrade
    if not noconfirm:
        print()
        if pacman_packages:
            print(color_line("New packages will be installed:", 12))
            print(format_paragraph(' '.join(pacman_packages)))
        if aur_packages:
            print(color_line("New packages will be installed from AUR:", 14))
            print(format_paragraph(' '.join(aur_packages)))
        if new_aur_deps:
            print(color_line(
                "New dependencies will be installed from AUR:", 11
            ))
            print(format_paragraph(' '.join(new_aur_deps)))
        print()

        answer = input('{} {}'.format(
            color_line('::', 12),
            bold_line('Proceed with installation? [Y/n] '),
        ))
        if answer:
            if answer.lower()[0] != 'y':
                sys.exit(1)

    all_aur_package_names = aur_packages + new_aur_deps
    package_builds = None
    if all_aur_package_names:
        try:
            package_builds = clone_pkgbuilds_git_repos(all_aur_package_names)
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

    # review PKGBUILD and install files
    # @TODO: ask about package conflicts/provides
    # 1) check if new_pkgs.{conflicts,provides} not in local_pkg.name
    # 2) check if new_pkgs.name not local_pkgs.{conflicsts,provides}
    local_packages_found, _ = find_local_packages(
        all_aur_package_names
    )
    for pkg_name in reversed(all_aur_package_names):
        repo_status = package_builds[pkg_name]
        repo_path = repo_status.repo_path
        already_installed = repo_status.check_installed_status(
            local_packages_found
        )

        if not (args.needed and already_installed):
            editor = get_editor()
            if editor:
                if ask_to_continue(
                        "Do you want to edit PKGBUILD for {} package?".format(
                            bold_line(pkg_name)
                        ),
                        default_yes=False
                ):
                    interactive_spawn([
                        get_editor(),
                        os.path.join(
                            repo_path,
                            'PKGBUILD'
                        )
                    ])
                    SrcInfo(repo_path).regenerate()

                install_file_name = SrcInfo(repo_path).get_install_script()
                if install_file_name:
                    if ask_to_continue(
                            "Do you want to edit {} for {} package?".format(
                                install_file_name,
                                bold_line(pkg_name)
                            ),
                            default_yes=False
                    ):
                        interactive_spawn([
                            get_editor(),
                            os.path.join(
                                repo_path,
                                install_file_name
                            )
                        ])

        else:
            print(
                '{} {} {}'.format(
                    color_line('warning:', 11),
                    pkg_name,
                    'is up to date -- skipping'
                )
            )

    # get sudo for further questions:
    interactive_spawn([
        'sudo', 'true'
    ])

    # build packages:
    for pkg_name in reversed(all_aur_package_names):
        repo_status = package_builds[pkg_name]
        if args.needed and repo_status.already_installed:
            continue
        try:
            repo_status.build(args)
        except BuildError:
            print(color_line(f"Can't build '{pkg_name}'.", 9))
            failed_to_build.append(pkg_name)
            # if not ask_to_continue():
            #     sys.exit(1)

    # install packages:

    if pacman_packages:
        if not retry_interactive_command(
                [
                    'sudo',
                    'pacman',
                    '-S',
                    '--noconfirm',
                ] + args._unknown_args +
                pacman_packages,
        ):
            if not ask_to_continue(default_yes=False):
                sys.exit(1)

    if args.downloadonly:
        return

    new_aur_deps_to_install = [
        package_builds[pkg_name].built_package_path
        for pkg_name in new_aur_deps
        if package_builds[pkg_name].built_package_path
    ]
    if new_aur_deps_to_install:
        if not retry_interactive_command(
                [
                    'sudo',
                    'pacman',
                    '-U',
                    '--asdeps',
                    '--noconfirm',
                ] + args._unknown_args +
                new_aur_deps_to_install,
        ):
            if not ask_to_continue(default_yes=False):
                sys.exit(1)

    aur_packages_to_install = [
        package_builds[pkg_name].built_package_path
        for pkg_name in aur_packages
        if package_builds[pkg_name].built_package_path
    ]
    if aur_packages_to_install:
        if not retry_interactive_command(
                [
                    'sudo',
                    'pacman',
                    '-U',
                    '--noconfirm',
                ] + args._unknown_args +
                aur_packages_to_install,
        ):
            if not ask_to_continue(default_yes=False):
                sys.exit(1)

    # save git hash of last sucessfully installed package
    if package_builds:
        for pkg_name, repo_status in package_builds.items():
            shutil.copy2(
                os.path.join(
                    repo_status.repo_path,
                    '.git/refs/heads/master'
                ),
                os.path.join(
                    repo_status.repo_path,
                    'last_installed.txt'
                )
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
        interactive_spawn(['sudo', 'pacman', '-Sy'])
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

    return cli_install_packages(
        args=args,
        packages=all_upgradeable_package_names,
        noconfirm=True
    )


def cli_info_packages(args):
    pkgs = 'pkgs'
    aur = 'aur'
    result = MultipleTasksExecutor({
        pkgs: PacmanColorTaskWorker(args._raw),
        aur: AurTaskWorkerInfo(
            packages=args._positional or []
        ),
    }).execute()
    json_results = result[aur].json['results']
    num_found = len(json_results)
    if result[pkgs].stdout:
        print(result[pkgs].stdout, end='\n' if json_results else '')
    for i, result in enumerate(json_results):
        print(
            '\n'.join([
                '{key:30}: {value}'.format(
                    key=bold_line(key),
                    value=value
                )
                for key, value in result.items()
            ]) + ('\n' if i+1 < num_found else '')
        )


def cli_clean_packages_cache(_args):
    print(_args)
    # @TODO: implement -Sc and -Scc
    raise NotImplementedError()


def cli_search_packages(args):
    pkgs = 'pkgs'
    aur = 'aur'
    result = MultipleTasksExecutor({
        pkgs: PacmanColorTaskWorker(args._raw),
        aur: AurTaskWorkerSearch(
            search_query=' '.join(args._positional or [])
        ),
    }).execute()

    print(result[pkgs].stdout, end='')
    for aur_pkg in result[aur].json['results']:
        if args.quiet:
            print(aur_pkg['Name'])
        else:
            print("{}{} {} {}".format(
                # color_line('aur/', 13),
                color_line('aur/', 9),
                bold_line(aur_pkg['Name']),
                color_line(aur_pkg["Version"], 10),
                '',  # [installed]
            ))
            print(format_paragraph(f'{aur_pkg["Description"]}'))
        # print(aur_pkg)


class SafeArgumentParser(argparse.ArgumentParser):

    def error(self, message):
        exc = sys.exc_info()[1]
        if exc:
            raise exc
        super().error(message)


def parse_args(args):
    parser = SafeArgumentParser(prog=sys.argv[0], add_help=False)

    for letter, opt in (
            ('S', 'sync'),
            ('c', 'clean'),
            ('i', 'info'),
            ('w', 'downloadonly'),
            ('q', 'quiet'),
            ('h', 'help'),
            ('s', 'search'),
            ('u', 'sysupgrade'),
            ('y', 'refresh'),
            #
            ('Q', 'query'),
            ('V', 'version'),
    ):
        parser.add_argument('-'+letter, '--'+opt, action='store_true')

    for opt in (
            'noconfirm',
            'needed',
    ):
        parser.add_argument('--'+opt, action='store_true')

    parser.add_argument('--ignore', action='append')
    parser.add_argument('_positional', nargs='*')

    parsed_args, unknown_args = parser.parse_known_args(args)
    parsed_args._unknown_args = unknown_args
    parsed_args._raw = args

    # print("ARGPARSE:")
    # print(parsed_args)
    # print(f'args = {args}')
    # reconstructed_args = {
    #    f'--{key}' if len(key) > 1 else f'-{key}': value
    #    for key, value in parsed_args.__dict__.items()
    #    if not key.startswith('_')
    #    if value
    # }
    # print(reconstructed_args)
    # print(unknown_args)
    # sys.exit(0)

    return parsed_args


def main():
    # pylint: disable=too-many-branches
    raw_args = sys.argv[1:]
    args = parse_args(raw_args)

    not_implemented_in_pikaur = False

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
        else:
            not_implemented_in_pikaur = True

    elif args.query:
        if args.sysupgrade:
            cli_print_upgradeable(args)
        else:
            interactive_spawn(['pacman', ] + raw_args)

    elif args.help:
        interactive_spawn(['pacman', ] + raw_args)
    elif args.version:
        print_version()
    else:
        not_implemented_in_pikaur = True

    if not_implemented_in_pikaur:
        interactive_spawn(['sudo', 'pacman', ] + raw_args)


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
