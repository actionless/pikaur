#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
# import argparse
import readline

from .args import parse_args
from .core import (
    SingleTaskExecutor, MultipleTasksExecutor,
    CmdTaskWorker, interactive_spawn, remove_dir,
)
from .pprint import (
    color_line, bold_line,
    print_upgradeable, pretty_format_upgradeable,
    print_not_found_packages, print_aur_search_results,
    print_version,
)
from .aur import (
    AurTaskWorkerSearch, AurTaskWorkerInfo,
)
from .pacman import (
    PacmanColorTaskWorker, PackageDB,
)
from .package_update import find_repo_updates, find_aur_updates
from .install_cli import InstallPackagesCLI, exclude_ignored_packages
from .prompt import retry_interactive_command_or_exit, ask_to_continue
from .config import BUILD_CACHE


REPO = 'repo'
AUR = 'aur'
LOCAL = 'local'


def init_readline():
    # follow GNU readline config in prompts:
    system_inputrc_path = '/etc/inputrc'
    if os.path.exists(system_inputrc_path):
        readline.read_init_file(system_inputrc_path)
    user_inputrc_path = os.path.expanduser('~/.inputrc')
    if os.path.exists(user_inputrc_path):
        readline.read_init_file(user_inputrc_path)


init_readline()


def cli_print_upgradeable(args):
    updates, _not_found_aur_pkgs = find_aur_updates()
    updates += find_repo_updates()
    if args.quiet:
        print_upgradeable(updates)
    else:
        print(pretty_format_upgradeable(updates))


def cli_install_packages(args, packages=None):
    InstallPackagesCLI(args=args, packages=packages)


def cli_upgrade_packages(args):
    if args.refresh:
        retry_interactive_command_or_exit(
            ['sudo', 'pacman', '--sync', '--refresh']
        )
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
    aur_updates, not_found_aur_pkgs = find_aur_updates()
    exclude_ignored_packages(not_found_aur_pkgs, args)
    if not_found_aur_pkgs:
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
    all_package_names = list(set(all_upgradeable_package_names + args.positional))
    if all_package_names:
        cli_install_packages(
            args=args,
            packages=all_package_names,
        )
    else:
        print('\n{} {}'.format(
            color_line('::', 10),
            bold_line('Already up-to-date.')
        ))


def cli_info_packages(args):
    result = MultipleTasksExecutor({
        REPO: PacmanColorTaskWorker(args.raw),
        AUR: AurTaskWorkerInfo(
            packages=args.positional or []
        ),
    }).execute()
    aur_pkgs = result[AUR]
    num_found = len(aur_pkgs)
    if result[REPO].stdout:
        print(result[REPO].stdout, end='\n' if aur_pkgs else '')
    for i, aur_pkg in enumerate(aur_pkgs):
        print(
            '\n'.join([
                '{key:24}: {value}'.format(
                    key=bold_line(key),
                    value=value if not isinstance(value, list)
                    else ', '.join(value)
                )
                for key, value in aur_pkg.__dict__.items()
            ]) + ('\n' if i+1 < num_found else '')
        )


def cli_clean_packages_cache(args):
    if os.path.exists(BUILD_CACHE):
        print(f'\nBuild directory: {BUILD_CACHE}')
        if ask_to_continue("{} Do you want to remove all files?".format(
                color_line('::', 12)
        )):
            remove_dir(BUILD_CACHE)
    sys.exit(
        interactive_spawn(['sudo', 'pacman', ] + args.raw).returncode
    )


def cli_search_packages(args):

    class GetLocalPkgsVersionsTask():
        async def get_task(self):
            return {
                pkg_name: pkg.version
                for pkg_name, pkg in PackageDB.get_local_dict().items()
            }

    tasks = {
        REPO: PacmanColorTaskWorker(args.raw),
        LOCAL: GetLocalPkgsVersionsTask,
    }
    tasks.update({
        AUR+search_word: AurTaskWorkerSearch(search_query=search_word)
        for search_word in (args.positional or [])
    })
    result = MultipleTasksExecutor(tasks).execute()
    local_pkgs_versions = result[LOCAL]

    all_aur_results = {
        key: search_results for key, search_results in result.items()
        if key.startswith(AUR)
    }
    aur_pkgs_nameset = None
    for key, search_results in all_aur_results.items():
        new_aur_pkgs_nameset = set([result.Name for result in search_results])
        if aur_pkgs_nameset:
            aur_pkgs_nameset = aur_pkgs_nameset.intersection(new_aur_pkgs_nameset)
        else:
            aur_pkgs_nameset = new_aur_pkgs_nameset
    aur_result = {
        result.Name: result
        for key, search_results in all_aur_results.items()
        for result in search_results
        if result.Name in aur_pkgs_nameset
    }.values()

    if result[REPO].stdout != '':
        print(result[REPO].stdout)
    print_aur_search_results(
        aur_results=aur_result,
        local_pkgs_versions=local_pkgs_versions,
        args=args
    )


def cli_print_version():
    pacman_version = SingleTaskExecutor(CmdTaskWorker(
        ['pacman', '--version', ],
    )).execute().stdout.splitlines()[1].strip(' .-')
    print_version(pacman_version)


def cli_print_help(args):
    pacman_help = SingleTaskExecutor(CmdTaskWorker(
        ['pacman', ] + args.raw,
    )).execute().stdout.replace(
        'pacman', 'pikaur'
    ).replace(
        'options:', '\nCommon Pacman options:'
    )
    pikaur_options_help = (
        ('', '--noedit', "don't prompt to edit PKGBUILDs and other build files"),
    )
    print("\n{}{}{}".format(
        pacman_help,
        "\n\nPikaur-specific options:\n" if pikaur_options_help else '',
        '\n'.join([
            "{:>5} {:<16} {}".format(short_opt or '', long_opt or '', descr)
            for short_opt, long_opt, descr in pikaur_options_help
        ])
    ))


def cli_entry_point():
    # pylint: disable=too-many-branches
    raw_args = sys.argv[1:]
    args = parse_args(raw_args)

    not_implemented_in_pikaur = False
    require_sudo = True

    if args.version:
        cli_print_version()
    elif args.help:
        cli_print_help(args)

    elif args.sync:
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

    else:
        not_implemented_in_pikaur = True

    if not_implemented_in_pikaur:
        if require_sudo:
            sys.exit(
                interactive_spawn(['sudo', 'pacman', ] + raw_args).returncode
            )
        sys.exit(
            interactive_spawn(['pacman', ] + raw_args).returncode
        )


def main():
    if os.getuid() == 0:
        print("{} {}".format(
            color_line('::', 9),
            "Don't run me as root."
        ))
        sys.exit(1)
    try:
        cli_entry_point()
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        sys.exit(0)


if __name__ == '__main__':
    main()
