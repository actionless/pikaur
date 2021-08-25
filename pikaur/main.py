#!/usr/bin/python3
# -*- coding: utf-8 -*-

""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import os
import sys
import readline
import signal
import codecs
import shutil
import atexit
import io
from argparse import ArgumentError  # pylint: disable=no-name-in-module
from typing import List, Optional, Callable

import pyalpm

from .i18n import _  # keep that first
from .args import (
    parse_args, reconstruct_args,
)
from .help_cli import cli_print_help
from .core import (
    DEFAULT_INPUT_ENCODING, InstallInfo,
    spawn, interactive_spawn, remove_dir, check_runtime_deps,
    running_as_root, sudo, isolate_root_cmd, run_with_sudo_loop,
)
from .pprint import (
    color_line, bold_line,
    print_stderr, print_stdout,
    print_error, print_warning, print_debug,
)
from .print_department import (
    pretty_format_upgradeable, print_version,
    print_ignored_package,
)
from .updates import find_repo_upgradeable, find_aur_updates
from .prompt import ask_to_continue, get_multiple_numbers_input, NotANumberInput
from .config import (
    BUILD_CACHE_PATH, PACKAGE_CACHE_PATH, CACHE_ROOT, CONFIG_PATH,
    AUR_REPOS_CACHE_PATH, PikaurConfig, _OLD_AUR_REPOS_CACHE_PATH, DATA_ROOT,
)
from .exceptions import SysExit
from .pikspect import TTYRestore, PikspectSignalHandler
from .install_cli import InstallPackagesCLI
from .search_cli import cli_search_packages
from .info_cli import cli_info_packages
from .pacman import PacmanConfig, get_ignored_pkgnames_from_patterns
from .urllib import init_proxy, ProxyInitSocks5Error
from .getpkgbuild_cli import cli_getpkgbuild


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
        real_stream = getattr(sys, attr)
        try:
            setattr(
                sys, attr,
                codecs.open(  # pylint: disable=consider-using-with
                    real_stream.fileno(),
                    mode='w', buffering=0, encoding=DEFAULT_INPUT_ENCODING
                )
            )
        except io.UnsupportedOperation:
            pass
        else:
            getattr(sys, attr).buffer = real_stream.buffer


init_output_encoding()


def cli_print_upgradeable() -> None:
    args = parse_args()
    updates: List[InstallInfo] = []
    if not args.repo:
        aur_updates, _not_found_aur_pkgs = find_aur_updates()
        updates += aur_updates
    if not args.aur:
        updates += find_repo_upgradeable()
    if not updates:
        return
    ignored_pkg_names = get_ignored_pkgnames_from_patterns(
        [pkg.name for pkg in updates],
        args.ignore + PacmanConfig().options.get('IgnorePkg', [])
    )
    for pkg in updates[:]:
        if pkg.name in ignored_pkg_names:
            updates.remove(pkg)
            print_ignored_package(install_info=pkg)
    if args.quiet:
        print_stdout('\n'.join([
            pkg_update.name for pkg_update in updates
        ]))
    else:
        print_stdout(pretty_format_upgradeable(
            updates,
            print_repo=PikaurConfig().sync.AlwaysShowPkgOrigin.get_bool()
        ))


def cli_install_packages() -> None:
    InstallPackagesCLI()


def cli_pkgbuild() -> None:
    cli_install_packages()


def cli_clean_packages_cache() -> None:
    args = parse_args()
    if not args.repo:
        for directory, message, minimal_clean_level in (
                (BUILD_CACHE_PATH, _("Build directory"), 1, ),
                (PACKAGE_CACHE_PATH, _("Packages directory"), 2, ),
        ):
            if minimal_clean_level <= args.clean and os.path.exists(directory):
                print_stdout('\n' + "{}: {}".format(message, directory))
                if ask_to_continue(text='{} {}'.format(
                        color_line('::', 12),
                        bold_line(_("Do you want to remove all files?"))
                )):
                    remove_dir(directory)
    if not args.aur:
        raise SysExit(
            interactive_spawn(sudo(
                [PikaurConfig().misc.PacmanPath.get_str(), ] + reconstruct_args(args)
            )).returncode
        )


def cli_print_version() -> None:
    args = parse_args()
    pacman_version = spawn(
        [PikaurConfig().misc.PacmanPath.get_str(), '--version', ],
    ).stdout_text.splitlines()[1].strip(' .-')
    print_version(
        pacman_version=pacman_version, pyalpm_version=pyalpm.version(),
        quiet=args.quiet
    )


def cli_dynamic_select() -> None:  # pragma: no cover
    packages = cli_search_packages(enumerated=True)
    if not packages:
        raise SysExit(1)

    while True:
        try:
            print_stderr(
                '\n' + _(
                    "Please enter the number of the package(s) you want to install "
                    "and press [Enter] (default={}):"
                ).format(1)
            )
            answers = get_multiple_numbers_input('> ', list(range(1, len(packages) + 1))) or [1]
            print_stderr()
            selected_pkgs_idx = [idx - 1 for idx in answers]
            restart_prompt = False
            for idx in selected_pkgs_idx:
                if not 0 <= idx < len(packages):
                    print_error(_('invalid value: {} is not between {} and {}').format(
                        idx + 1, 1, len(packages) + 1
                    ))
                    restart_prompt = True
            if restart_prompt:
                continue
            break
        except NotANumberInput as exc:
            if exc.character.lower() == _('n'):
                raise SysExit(128) from exc
            print_error(_('invalid number: {}').format(exc.character))

    parse_args().positional = [packages[idx].name for idx in selected_pkgs_idx]
    cli_install_packages()


def cli_entry_point() -> None:  # pylint: disable=too-many-statements
    # pylint: disable=too-many-branches

    try:
        init_proxy()
    except ProxyInitSocks5Error as exc:
        print_error(''.join(exc.args))
        sys.exit(2)

    # operations are parsed in order what the less destructive (like info and query)
    # are being handled first, for cases when user by mistake
    # specified both operations, like `pikaur -QS smth`

    args = parse_args()
    pikaur_operation: Optional[Callable] = None
    require_sudo = False

    if args.help:
        pikaur_operation = cli_print_help

    elif args.version:
        pikaur_operation = cli_print_version

    elif args.query:
        if args.sysupgrade:
            pikaur_operation = cli_print_upgradeable

    elif args.files:
        require_sudo = bool(args.refresh)

    elif args.getpkgbuild:
        pikaur_operation = cli_getpkgbuild

    elif args.pkgbuild:
        require_sudo = True
        pikaur_operation = cli_pkgbuild

    elif args.sync:
        if args.search:
            pikaur_operation = cli_search_packages
        elif args.info:
            pikaur_operation = cli_info_packages
        elif args.clean:
            if not args.aur:
                require_sudo = True
            pikaur_operation = cli_clean_packages_cache
        elif args.groups or args.list:   # @TODO: implement -l/--list
            require_sudo = False
        else:
            require_sudo = True
            pikaur_operation = cli_install_packages

    elif not (args.database or args.remove or args.deptest or args.upgrade):
        if args.positional:
            pikaur_operation = cli_dynamic_select

    else:
        require_sudo = True

    if pikaur_operation:
        print_debug(f"Pikaur operation found for {sys.argv=}: {pikaur_operation.__name__}")
        if require_sudo and args.dynamic_users and not running_as_root():
            # Restart pikaur with sudo to use systemd dynamic users
            restart_args = sys.argv[:]
            config_overridden = max([
                arg.startswith('--pikaur-config')
                for arg in restart_args
            ])
            if not config_overridden:
                restart_args += ['--pikaur-config', CONFIG_PATH]
            sys.exit(interactive_spawn(
                sudo(restart_args)
            ).returncode)
        else:
            if not require_sudo or running_as_root():
                # Just run the operation normally
                pikaur_operation()
            else:
                # Or use sudo loop if not running as root but need to have it later
                run_with_sudo_loop(pikaur_operation)
    else:
        # Just bypass all the args to pacman
        print_debug(f"Pikaur operation not found for {sys.argv=}")
        print_debug(args)
        pacman_args = [
            PikaurConfig().misc.PacmanPath.get_str(),
        ] + args.raw_without_pikaur_specific
        if require_sudo:
            pacman_args = sudo(pacman_args)
        sys.exit(
            interactive_spawn(pacman_args).returncode
        )


def migrate_old_aur_repos_dir() -> None:
    if not (
            os.path.exists(_OLD_AUR_REPOS_CACHE_PATH) and not os.path.exists(AUR_REPOS_CACHE_PATH)
    ):
        return
    if not os.path.exists(DATA_ROOT):
        os.makedirs(DATA_ROOT)
    shutil.move(_OLD_AUR_REPOS_CACHE_PATH, AUR_REPOS_CACHE_PATH)

    print_stderr()
    print_warning(
        _("AUR repos dir has been moved from '{old}' to '{new}'.".format(
            old=_OLD_AUR_REPOS_CACHE_PATH,
            new=AUR_REPOS_CACHE_PATH
        ))
    )
    print_stderr()


def create_dirs() -> None:
    if running_as_root():
        # Let systemd-run setup the directories and symlinks
        true_cmd = isolate_root_cmd(['true'])
        result = spawn(true_cmd)
        if result.returncode != 0:
            raise Exception(result)
        # Chown the private CacheDirectory to root to signal systemd that
        # it needs to recursively chown it to the correct user
        os.chown(os.path.realpath(CACHE_ROOT), 0, 0)
    if not os.path.exists(CACHE_ROOT):
        os.makedirs(CACHE_ROOT)
    migrate_old_aur_repos_dir()
    if not os.path.exists(AUR_REPOS_CACHE_PATH):
        os.makedirs(AUR_REPOS_CACHE_PATH)


def restore_tty() -> None:
    TTYRestore.restore()


def handle_sig_int(*_whatever) -> None:  # pragma: no cover
    if signal_handler := PikspectSignalHandler.get():
        return signal_handler(*_whatever)  # pylint: disable=not-callable
    if parse_args().pikaur_debug:
        raise KeyboardInterrupt()
    print_stderr("\n\nCanceled by user (SIGINT)", lock=False)
    raise SysExit(125)


def main() -> None:
    try:
        parse_args()
    except ArgumentError as exc:
        print_stderr(exc)
        sys.exit(22)
    check_runtime_deps()

    create_dirs()
    # initialize config to avoid race condition in threads:
    PikaurConfig.get_config()

    atexit.register(restore_tty)
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    signal.signal(signal.SIGINT, handle_sig_int)

    try:
        cli_entry_point()
    except BrokenPipeError:
        # @TODO: should it be 32?
        sys.exit(0)
    except SysExit as exc:
        sys.exit(exc.code)
    sys.exit(0)


if __name__ == '__main__':
    main()
