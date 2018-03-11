#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import readline
import signal
import subprocess
from datetime import datetime
from typing import List, Tuple

from .i18n import _  # keep that first
from .args import parse_args, PikaurArgs
from .core import (
    SingleTaskExecutor, MultipleTasksExecutor, PackageSource,
    CmdTaskWorker, interactive_spawn, running_as_root, remove_dir,
)
from .pprint import (
    color_line, bold_line,
    print_status_message,
    pretty_format_upgradeable,
    print_not_found_packages,
    print_version,
)
from .pacman import PacmanColorTaskWorker
from .aur import AURTaskWorkerInfo
from .package_update import (
    PackageUpdate,
    find_repo_updates, find_aur_updates,
)
from .prompt import retry_interactive_command_or_exit, ask_to_continue
from .config import CACHE_ROOT, BUILD_CACHE_DIR

from .install_cli import InstallPackagesCLI, exclude_ignored_packages
from .search_cli import cli_search_packages


def init_readline() -> None:
    # follow GNU readline config in prompts:
    system_inputrc_path = '/etc/inputrc'
    if os.path.exists(system_inputrc_path):
        readline.read_init_file(system_inputrc_path)
    user_inputrc_path = os.path.expanduser('~/.inputrc')
    if os.path.exists(user_inputrc_path):
        readline.read_init_file(user_inputrc_path)


init_readline()


def cli_print_upgradeable(args: PikaurArgs) -> None:
    updates: List[PackageUpdate] = []
    if not args.repo:
        aur_updates, _not_found_aur_pkgs = find_aur_updates()
        updates += aur_updates
    if not args.aur:
        updates += find_repo_updates()
    if args.quiet:
        print('\n'.join([
            pkg_update.Name for pkg_update in updates
        ]))
    else:
        print(pretty_format_upgradeable(updates))


def cli_install_packages(args, packages: List[str] = None) -> None:
    InstallPackagesCLI(args=args, packages=packages)


def cli_upgrade_packages(args: PikaurArgs) -> None:
    if args.refresh:
        retry_interactive_command_or_exit(
            ['sudo', 'pacman', '--sync', '--refresh']
        )
    ignore = args.ignore or []

    repo_packages_updates: List[PackageUpdate] = []
    if not args.aur:
        print('{} {}'.format(
            color_line('::', 12),
            bold_line(_("Starting full system upgrade..."))
        ))
        repo_packages_updates = [
            pkg for pkg in find_repo_updates()
            if pkg.Name not in ignore
        ]

    aur_updates: List[PackageUpdate] = []
    if not args.repo:
        print('{} {}'.format(
            color_line('::', 12),
            bold_line(_("Starting full AUR upgrade..."))
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
            bold_line(_("Already up-to-date."))
        ))


def cli_info_packages(args: PikaurArgs) -> None:
    result = MultipleTasksExecutor({
        str(PackageSource.REPO): PacmanColorTaskWorker(args.raw),
        str(PackageSource.AUR): AURTaskWorkerInfo(
            packages=args.positional or []
        ),
    }).execute()
    aur_pkgs = result[str(PackageSource.AUR)]
    num_found = len(aur_pkgs)
    if result[str(PackageSource.REPO)].stdout:
        print(result[str(PackageSource.REPO)].stdout, end='\n' if aur_pkgs else '')
    for i, aur_pkg in enumerate(aur_pkgs):
        pkg_info_lines = []
        for key, value in aur_pkg.__dict__.items():
            if key in ['firstsubmitted', 'lastmodified']:
                value = datetime.fromtimestamp(value).strftime('%c')
            elif isinstance(value, list):
                value = ', '.join(value)
            pkg_info_lines.append('{key:24}: {value}'.format(
                key=bold_line(key), value=value))
        print('\n'.join(pkg_info_lines) + ('\n' if i+1 < num_found else ''))


def cli_clean_packages_cache(args: PikaurArgs) -> None:
    build_cache = os.path.join(CACHE_ROOT, BUILD_CACHE_DIR)
    if os.path.exists(build_cache):
        print('\n' + _("Build directory: {}").format(build_cache))
        if ask_to_continue('{} {}'.format(
                color_line('::', 12),
                _("Do you want to remove all files?")
        )):
            remove_dir(build_cache)
    sys.exit(
        interactive_spawn(['sudo', 'pacman', ] + args.raw).returncode
    )


def cli_print_version(args: PikaurArgs) -> None:
    pacman_version = SingleTaskExecutor(CmdTaskWorker(
        ['pacman', '--version', ],
    )).execute().stdout.splitlines()[1].strip(' .-')
    print_version(pacman_version, quiet=args.quiet)


def cli_print_help(args: PikaurArgs) -> None:
    pacman_help = SingleTaskExecutor(CmdTaskWorker(
        ['pacman', ] + args.raw,
    )).execute().stdout.replace(
        'pacman', 'pikaur'
    ).replace(
        'options:', '\n' + _("Common pacman options:")
    )
    pikaur_options_help: List[Tuple[str, str, str]] = []
    if args.sync:
        pikaur_options_help += [
            ('', '--noedit', _("don't prompt to edit PKGBUILDs and other build files")),
            ('', '--namesonly', _("search only in package names")),
        ]
    if args.sync or args.query:
        pikaur_options_help += [
            ('', '--repo', _("query packages from repository only")),
            ('', '--aur', _("query packages from AUR only")),
        ]
    print(''.join([
        '\n',
        pacman_help,
        '\n\n' + _('Pikaur-specific options:') + '\n' if pikaur_options_help else '',
        '\n'.join([
            '{:>5} {:<16} {}'.format(
                short_opt or '', long_opt or '', descr
            )
            for short_opt, long_opt, descr in pikaur_options_help
        ])
    ]))


def cli_entry_point() -> None:
    # pylint: disable=too-many-branches
    raw_args = sys.argv[1:]
    args = parse_args(raw_args)

    not_implemented_in_pikaur = False
    require_sudo = True

    if args.version:
        cli_print_version(args)
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
        if require_sudo and raw_args:
            sys.exit(
                interactive_spawn(['sudo', 'pacman', ] + raw_args).returncode
            )
        sys.exit(
            interactive_spawn(['pacman', ] + raw_args).returncode
        )


def check_systemd_dynamic_users() -> bool:
    try:
        out = subprocess.check_output(['systemd-run', '--version'],
                                      universal_newlines=True)
    except FileNotFoundError:
        return False
    first_line = out.split('\n')[0]
    version = int(first_line.split()[1])
    return version >= 235


def main() -> None:
    if running_as_root() and not check_systemd_dynamic_users():
        print_status_message("{} {}".format(
            color_line('::', 9),
            _("pikaur requires systemd >= 235 (dynamic users) to be run as root."),
        ))
        sys.exit(1)

    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    try:
        cli_entry_point()
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        sys.exit(0)


if __name__ == '__main__':
    main()
