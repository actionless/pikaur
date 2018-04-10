#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import readline
import signal
import subprocess
import codecs
from datetime import datetime
from typing import List
from multiprocessing.pool import ThreadPool

from .i18n import _  # keep that first
from .args import (
    PikaurArgs,
    parse_args, reconstruct_args, cli_print_help
)
from .core import (
    PackageSource,
    spawn, interactive_spawn, running_as_root, remove_dir,
)
from .pprint import (
    color_line, bold_line,
    print_status_message,
    pretty_format_upgradeable,
    print_version,
)
from .pacman import (
    PACMAN_COLOR_ARGS,
)
from .aur import (
    aur_rpc_info,
)
from .package_update import (
    PackageUpdate,
    find_repo_updates, find_aur_updates,
)
from .prompt import (
    retry_interactive_command_or_exit, ask_to_continue,
)
from .config import (
    CACHE_ROOT, BUILD_CACHE_DIR,
)
from .install_cli import (
    InstallPackagesCLI,
)
from .search_cli import (
    cli_search_packages,
)


def init_readline() -> None:
    # follow GNU readline config in prompts:
    system_inputrc_path = '/etc/inputrc'
    if os.path.exists(system_inputrc_path):
        readline.read_init_file(system_inputrc_path)
    user_inputrc_path = os.path.expanduser('~/.inputrc')
    if os.path.exists(user_inputrc_path):
        readline.read_init_file(user_inputrc_path)


init_readline()


def init_output_encoding() -> None:
    for attr in ('stdout', 'stderr'):
        setattr(
            sys, attr,
            codecs.open(
                getattr(sys, attr).fileno(),
                mode='w', buffering=0, encoding='utf-8'
            )
        )


init_output_encoding()


def cli_print_upgradeable(args: PikaurArgs) -> None:
    updates: List[PackageUpdate] = []
    if not args.repo:
        aur_updates, _not_found_aur_pkgs = find_aur_updates(args)
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
            ['sudo', 'pacman', '--sync', '--refresh'],
            args=args
        )
    if not args.repo:
        print('{} {}'.format(
            color_line('::', 12),
            bold_line(_("Starting full AUR upgrade..."))
        ))
    cli_install_packages(
        args=args,
        packages=args.positional,
    )


def _info_packages_thread_repo(
        raw_args: List[str]
) -> str:
    return interactive_spawn(
        PACMAN_COLOR_ARGS + raw_args,
        stderr=subprocess.DEVNULL,
        stdout=subprocess.PIPE
    ).stdout_text


def cli_info_packages(args: PikaurArgs) -> None:
    with ThreadPool() as pool:
        requests = {}
        requests[PackageSource.AUR] = pool.apply_async(aur_rpc_info, (args.positional or [], ))
        requests[PackageSource.REPO] = pool.apply_async(_info_packages_thread_repo, (args.raw, ))
        pool.close()
        pool.join()
        result = {
            key: value.get()
            for key, value in requests.items()
        }

    if result[PackageSource.REPO]:
        print(result[PackageSource.REPO], end='')

    aur_pkgs = result[PackageSource.AUR]
    num_found = len(aur_pkgs)
    for i, aur_pkg in enumerate(aur_pkgs):
        pkg_info_lines = []
        for key, value in aur_pkg.__dict__.items():
            if key in ['firstsubmitted', 'lastmodified']:
                value = datetime.fromtimestamp(value).strftime('%c')
            elif isinstance(value, list):
                value = ', '.join(value)
            pkg_info_lines.append('{key:24}: {value}'.format(
                key=bold_line(key), value=value))
        print('\n'.join(pkg_info_lines) + ('\n' if i + 1 < num_found else ''))


def cli_clean_packages_cache(args: PikaurArgs) -> None:
    if not args.repo:
        # @TODO: flush ~/.cache/pikaur/pkg on -Scc
        build_cache = os.path.join(CACHE_ROOT, BUILD_CACHE_DIR)
        if os.path.exists(build_cache):
            print('\n' + _("Build directory: {}").format(build_cache))
            if ask_to_continue(args=args, text='{} {}'.format(
                    color_line('::', 12),
                    _("Do you want to remove all files?")
            )):
                remove_dir(build_cache)
    if not args.aur:
        sys.exit(
            interactive_spawn(
                ['sudo', 'pacman', ] + reconstruct_args(args, ['--repo'])
            ).returncode
        )


def cli_print_version(args: PikaurArgs) -> None:
    pacman_version = spawn(
        ['pacman', '--version', ],
    ).stdout_text.splitlines()[1].strip(' .-')
    print_version(pacman_version, quiet=args.quiet)


def cli_entry_point() -> None:
    # pylint: disable=too-many-branches
    # @TODO: parse args right in the .args module
    raw_args = sys.argv[1:]
    args = parse_args(raw_args)

    not_implemented_in_pikaur = False
    require_sudo = True

    if args.help:
        cli_print_help(args)
    elif args.version:
        cli_print_version(args)

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
    if running_as_root():
        print_status_message("{} {}".format(
            color_line('::', 9),
            _("don't run me as root."),
        ))
        sys.exit(65)
    # @TODO: either fix this or remove:
    if running_as_root() and not check_systemd_dynamic_users():
        print_status_message("{} {}".format(
            color_line('::', 9),
            _("pikaur requires systemd >= 235 (dynamic users) to be run as root."),
        ))
        sys.exit(65)

    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    try:
        cli_entry_point()
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        # @TODO: should it be 32?
        sys.exit(0)


if __name__ == '__main__':
    main()
