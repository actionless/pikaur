#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import readline
import shutil
import glob

from .core import (
    SingleTaskExecutor, MultipleTasksExecutor,
    CmdTaskWorker, interactive_spawn,
    BUILD_CACHE,
)
from .pprint import (
    color_line, format_paragraph,
    print_not_found_packages,
    print_upgradeable, pretty_print_upgradeable,
)
from .aur import (
    AurTaskWorkerSearch,
    find_aur_packages, find_aur_updates
)
from .pacman import (
    PacmanColorTaskWorker,
    find_repo_packages, find_local_packages,
    find_packages_not_from_repo, find_repo_updates,
)
from .build import SrcInfo, PackageBuild


def init_readline():
    # follow GNU readline config in prompts:
    system_inputrc_path = '/etc/inputrc'
    if os.path.exists(system_inputrc_path):
        readline.read_init_file(system_inputrc_path)
    user_inputrc_path = os.path.expanduser('~/.inputrc')
    if os.path.exists(user_inputrc_path):
        readline.read_init_file(user_inputrc_path)


init_readline()


def ask_to_continue(text='Do you want to proceed?', default_yes=True):
    answer = input(text + (' [Y/n] ' if default_yes else ' [y/N] '))
    if default_yes:
        if answer and answer.lower()[0] != 'y':
            return False
    else:
        if not answer or answer.lower()[0] != 'y':
            return False
    return True


def clone_git_repos(package_names):
    repos_statuses = {
        package_name: PackageBuild(package_name)
        for package_name in package_names
    }
    results = MultipleTasksExecutor({
        repo_status.package_name: repo_status.create_task()
        for repo_status in repos_statuses.values()
    }).execute()
    for package_name, result in results.items():
        if result.return_code > 0:
            print(color_line(f"Can't clone '{package_name}' from AUR:", 9))
            print(result)
            if not ask_to_continue():
                sys.exit(1)
    return repos_statuses


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
            dep.split('=')[0].split('<')[0].split('>')[0] for dep in
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

        aur_deps_for_aur_packages = []
        if all_deps_for_aur_packages:
            _, not_found_deps = find_repo_packages(
                all_deps_for_aur_packages
            )
            if not_found_deps:
                _local_pkgs_info, aur_deps_for_aur_packages = \
                    find_local_packages(
                        not_found_deps
                    )
                _aur_deps_info, not_found_aur_deps = find_aur_packages(
                    aur_deps_for_aur_packages
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
                        color_line(
                            'Dependencies missing for '
                            f'{problem_package_names}',
                            15
                        ),
                    ))
                    print_not_found_packages(not_found_aur_deps)
                    sys.exit(1)
        new_aur_deps += aur_deps_for_aur_packages
        package_names = aur_deps_for_aur_packages

    return new_aur_deps


def cli_install_packages(args, noconfirm=None, packages=None):
    # @TODO: split into smaller routines
    if noconfirm is None:
        noconfirm = args.noconfirm
    print("resolving dependencies...")
    packages = packages or args._positional
    if args.ignore:
        for ignored_pkg in args.ignore:
            packages.remove(ignored_pkg)
    pacman_packages, aur_packages = find_repo_packages(packages)
    new_aur_deps = find_aur_deps(aur_packages)

    # confirm package install/upgrade
    if not noconfirm:
        print()
        # print(color_line("Package", 15))
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
            color_line('Proceed with installation? [Y/n] ', 15),
        ))
        if answer:
            if answer.lower()[0] != 'y':
                sys.exit(1)

    all_aur_package_names = aur_packages + new_aur_deps
    repos_statuses = None
    if all_aur_package_names:
        repos_statuses = clone_git_repos(all_aur_package_names)

    # review PKGBUILD and install files
    # @TODO: ask about package conflicts/provides
    local_packages_found, _ = find_local_packages(
        all_aur_package_names
    )
    for pkg_name in reversed(all_aur_package_names):
        repo_status = repos_statuses[pkg_name]
        repo_path = repo_status.repo_path

        last_installed_file_path = os.path.join(
            repo_path,
            'last_installed.txt'
        )
        already_installed = False
        if (
                pkg_name in local_packages_found
        ) and (
            os.path.exists(last_installed_file_path)
        ):
            with open(last_installed_file_path) as last_installed_file:
                last_installed_hash = last_installed_file.readlines()
                with open(
                    os.path.join(
                        repo_path,
                        '.git/refs/heads/master'
                    )
                ) as current_hash_file:
                    current_hash = current_hash_file.readlines()
                    if last_installed_hash == current_hash:
                        already_installed = True
        repo_status.already_installed = already_installed

        if not ('--needed' in args._raw and already_installed):
            editor = get_editor()
            if editor:
                if ask_to_continue(
                        "Do you want to edit PKGBUILD for {} package?".format(
                            color_line(pkg_name, 15)
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

                install_file_name = SrcInfo(repo_path).get_install_script()
                if install_file_name:
                    if ask_to_continue(
                            "Do you want to edit {} for {} package?".format(
                                install_file_name,
                                color_line(pkg_name, 15)
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

    # get sudo for further questions
    interactive_spawn([
        'sudo', 'true'
    ])

    # build packages
    for pkg_name in reversed(all_aur_package_names):
        repo_status = repos_statuses[pkg_name]

        if '--needed' in args._raw and repo_status.already_installed:
            continue
        repo_path = repo_status.repo_path
        build_dir = os.path.join(BUILD_CACHE, pkg_name)
        if os.path.exists(build_dir):
            try:
                shutil.rmtree(build_dir)
            except PermissionError:
                interactive_spawn(['rm', '-rf', build_dir])
        shutil.copytree(repo_path, build_dir)

        # @TODO: args._unknown_args
        make_deps = SrcInfo(repo_path).get_makedepends()
        _, new_make_deps_to_install = find_local_packages(make_deps)
        if new_make_deps_to_install:
            interactive_spawn(
                [
                    'sudo',
                    'pacman',
                    '-S',
                    '--asdeps',
                    '--noconfirm',
                ] + args._unknown_args +
                new_make_deps_to_install,
            )
        build_result = interactive_spawn(
            [
                'makepkg',
                # '-rsf', '--noconfirm',
                '--nodeps',
            ],
            cwd=build_dir
        )
        if new_make_deps_to_install:
            interactive_spawn(
                [
                    'sudo',
                    'pacman',
                    '-Rs',
                    '--noconfirm',
                ] + new_make_deps_to_install,
            )
        if build_result.returncode > 0:
            print(color_line(f"Can't build '{pkg_name}'.", 9))
            if not ask_to_continue():
                sys.exit(1)
        else:
            repo_status.built_package_path = glob.glob(
                os.path.join(build_dir, '*.pkg.tar.xz')
            )[0]

    if pacman_packages:
        interactive_spawn(
            [
                'sudo',
                'pacman',
                '-S',
                '--noconfirm',
            ] + args._unknown_args +
            pacman_packages,
        )

    if args.downloadonly:
        return

    new_aur_deps_to_install = [
        repos_statuses[pkg_name].built_package_path
        for pkg_name in new_aur_deps
        if repos_statuses[pkg_name].built_package_path
    ]
    if new_aur_deps_to_install:
        interactive_spawn(
            [
                'sudo',
                'pacman',
                '-U',
                '--asdeps',
                '--noconfirm',
            ] + args._unknown_args +
            new_aur_deps_to_install,
        )

    aur_packages_to_install = [
        repos_statuses[pkg_name].built_package_path
        for pkg_name in aur_packages
        if repos_statuses[pkg_name].built_package_path
    ]
    if aur_packages_to_install:
        interactive_spawn(
            [
                'sudo',
                'pacman',
                '-U',
                '--noconfirm',
            ] + args._unknown_args +
            aur_packages_to_install,
        )

    # save git hash of last sucessfully installed package
    if repos_statuses:
        for pkg_name, repo_status in repos_statuses.items():
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


def cli_print_upgradeable(args):
    updates, _ = find_aur_updates(find_packages_not_from_repo())
    updates += find_repo_updates()
    updates = sorted(updates, key=lambda u: u.pkg_name)
    if args.quiet:
        print_upgradeable(updates)
    else:
        pretty_print_upgradeable(updates)


def cli_upgrade_packages(args):
    if args.refresh:
        interactive_spawn(['sudo', 'pacman', '-Sy'])

    print('{} {}'.format(
        color_line('::', 12),
        color_line('Starting full system upgrade...', 15)
    ))
    repo_packages_updates = find_repo_updates()
    pretty_print_upgradeable(repo_packages_updates, ignore=args.ignore)

    print('\n{} {}'.format(
        color_line('::', 12),
        color_line('Starting full AUR upgrade...', 15)
    ))
    aur_updates, not_found_aur_pkgs = \
        find_aur_updates(find_packages_not_from_repo())
    print_not_found_packages(not_found_aur_pkgs)

    print('\n{} {}'.format(
        color_line('::', 12),
        color_line('AUR packages updates:', 15)
    ))
    pretty_print_upgradeable(aur_updates, ignore=args.ignore)

    print()
    answer = input('{} {}\n{} {}\n> '.format(
        color_line('::', 12),
        color_line('Proceed with installation? [Y/n] ', 15),
        color_line('::', 12),
        color_line('[V]iew package detail   [M]anually select packages', 15)
    ))
    if answer:
        if answer.lower()[0] != 'y':
            sys.exit(1)
    return cli_install_packages(
        args=args,
        packages=[u.pkg_name for u in repo_packages_updates] +
        [u.pkg_name for u in aur_updates],
        noconfirm=True
    )


def cli_info_packages(_args):
    # @TODO:
    raise NotImplementedError()


def cli_clean_packages_cache(_args):
    # @TODO:
    print(_args)
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
                color_line(aur_pkg['Name'], 15),
                color_line(aur_pkg["Version"], 10),
                '',  # [installed]
            ))
            print(format_paragraph(f'{aur_pkg["Description"]}'))
        # print(aur_pkg)


def cli_version():
    sys.stdout.buffer.write(r"""
      /:}               _
     /--1             / :}
    /   |           / `-/
   |  ,  --------  /   /
   |'                 Y
  /                   l     Pikaur v0.1
  l  /       \        l     (C) 2018 Pikaur development team
  j  ●   .   ●        l     Licensed under GPLv3
 { )  ._,.__,   , -.  {
  У    \  _/     ._/   \

""".encode())


def parse_args(args):
    parser = argparse.ArgumentParser(prog=sys.argv[0], add_help=False)
    for letter, opt in (
            ('S', 'sync'),
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
    ):
        parser.add_argument('--'+opt, action='store_true')
    for letter in (
            'b', 'c', 'd', 'g', 'i', 'l', 'p', 'r', 'v',
    ):
        parser.add_argument('-'+letter, action='store_true')
    parser.add_argument('_positional', nargs='*')
    parser.add_argument('--ignore', action='append')

    parsed_args, unknown_args = parser.parse_known_args(args)
    parsed_args._unknown_args = unknown_args
    parsed_args._raw = args

    # print(f'args = {args}')
    # print("ARGPARSE:")
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
    raw_args = sys.argv[1:]
    args = parse_args(raw_args)

    not_implemented_in_pikaur = False

    if args.sync:
        if args.sysupgrade:
            cli_upgrade_packages(args)
        elif args.search:
            cli_search_packages(args)
        elif args.i:
            cli_info_packages(args)
        elif args.c:
            cli_clean_packages_cache(args)
        elif '-S' in raw_args or '--sync' in raw_args:
            cli_install_packages(args)
        else:
            not_implemented_in_pikaur = True

    elif args.query:
        if args.sysupgrade:
            cli_print_upgradeable(args)
        else:
            not_implemented_in_pikaur = True

    elif args.help:
        interactive_spawn(['pacman', ] + raw_args)
    elif args.version:
        cli_version()
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
