#!/usr/bin/python3
# -*- coding: utf-8 -*-

""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import os
import sys
import readline
import signal
import subprocess
import codecs
import shutil
import atexit
import io
import socket
from argparse import ArgumentError  # pylint: disable=no-name-in-module
from typing import List, Optional, Callable, NoReturn

from .i18n import _  # keep that first
from .args import (
    parse_args, reconstruct_args, cli_print_help
)
from .core import (
    InstallInfo,
    spawn, interactive_spawn, remove_dir,
    running_as_root, sudo, isolate_root_cmd, run_with_sudo_loop,
)
from .pprint import color_line, bold_line, print_stderr, print_stdout, print_error
from .print_department import (
    pretty_format_upgradeable, print_version, print_not_found_packages,
)
from .updates import find_repo_upgradeable, find_aur_updates
from .prompt import ask_to_continue, get_input
from .config import (
    BUILD_CACHE_PATH, PACKAGE_CACHE_PATH, CACHE_ROOT, CONFIG_PATH,
    AUR_REPOS_CACHE_PATH, PikaurConfig, migrate_old_aur_repos_dir,
)
from .exceptions import SysExit
from .pikspect import TTYRestore
from .install_cli import InstallPackagesCLI
from .search_cli import cli_search_packages
from .info_cli import cli_info_packages
from .aur import find_aur_packages, get_repo_url
from .aur_deps import get_aur_deps_list
from .pacman import PackageDB, PackagesNotFoundInRepo


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
                codecs.open(
                    real_stream.fileno(),
                    mode='w', buffering=0, encoding='utf-8'
                )
            )
        except io.UnsupportedOperation:
            pass
        else:
            getattr(sys, attr).buffer = real_stream.buffer


init_output_encoding()


def init_proxy() -> None:
    proxy = PikaurConfig().network.Socks5Proxy.get_str()
    if proxy:  # pragma: no cover
        port = 1080
        idx = proxy.find(':')
        if idx >= 0:
            port = int(proxy[idx + 1:])
            proxy = proxy[:idx]

        try:
            import socks  # type: ignore #  pylint:disable=import-outside-toplevel
            socks.set_default_proxy(socks.PROXY_TYPE_SOCKS5, proxy, port)
            socket.socket = socks.socksocket  # type: ignore
        except ImportError:
            print_error(
                _("pikaur requires python-pysocks to use a socks5 proxy.")
            )
            sys.exit(2)


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


def cli_getpkgbuild() -> None:
    check_runtime_deps(['asp'])
    args = parse_args()
    pwd = os.path.abspath(os.path.curdir)
    aur_pkg_names = args.positional

    aur_pkgs, not_found_aur_pkgs = find_aur_packages(aur_pkg_names)
    repo_pkgs = []
    not_found_repo_pkgs = []
    for pkg_name in not_found_aur_pkgs:
        try:
            repo_pkg = PackageDB.find_repo_package(pkg_name)
        except PackagesNotFoundInRepo:
            not_found_repo_pkgs.append(pkg_name)
        else:
            repo_pkgs.append(repo_pkg)

    if not_found_repo_pkgs:
        print_not_found_packages(not_found_repo_pkgs)

    if args.deps:
        aur_pkgs = aur_pkgs + get_aur_deps_list(aur_pkgs)

    for aur_pkg in aur_pkgs:
        name = aur_pkg.name
        repo_path = os.path.join(pwd, name)
        print_stdout()
        interactive_spawn([
            'git',
            'clone',
            get_repo_url(aur_pkg.packagebase),
            repo_path,
        ])

    for repo_pkg in repo_pkgs:
        print_stdout()
        interactive_spawn([
            'asp',
            'checkout',
            repo_pkg.name,
        ])


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
                        _("Do you want to remove all files?")
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
    print_version(pacman_version, quiet=args.quiet)


def cli_dynamic_select() -> None:  # pragma: no cover
    packages = cli_search_packages(enumerated=True)
    if not packages:
        raise SysExit(1)

    print_stderr(
        '\n' +
        _("Please enter the number of the package you want to install (default={}):").format(
            1
        )
    )
    answer = get_input('> ', [str(i) for i in range(1, len(packages) + 1)]) or '1'
    print_stderr()
    if answer.lower() == _('n'):
        raise SysExit(128)

    try:
        selected_pkg_idx = int(answer) - 1
    except ValueError:
        print_error(_('invalid number: {}').format(answer))
        raise SysExit(5)

    if not 0 <= selected_pkg_idx < len(packages):
        print_error(_('invalid value: {} is not between {} and {}').format(
            answer, 1, len(packages)
        ))
        raise SysExit(5)

    parse_args().positional = [packages[selected_pkg_idx].name, ]
    cli_install_packages()


def cli_entry_point() -> None:  # pylint: disable=too-many-statements
    # pylint: disable=too-many-branches

    init_proxy()

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
        pacman_args = [PikaurConfig().misc.PacmanPath.get_str(), ] + (args.raw or [])
        if require_sudo:
            pacman_args = sudo(pacman_args)
        sys.exit(
            interactive_spawn(pacman_args).returncode
        )


def check_systemd_dynamic_users() -> bool:  # pragma: no cover
    try:
        out = subprocess.check_output(['systemd-run', '--version'],
                                      universal_newlines=True)
    except FileNotFoundError:
        return False
    first_line = out.split('\n')[0]
    version = int(first_line.split()[1])
    return version >= 235


def check_runtime_deps(dep_names: Optional[List[str]] = None) -> None:
    if sys.version_info.major < 3 or sys.version_info.minor < 7:
        print_error(
            _("pikaur requires Python >= 3.7 to run."),
        )
        sys.exit(65)
    if running_as_root() and not check_systemd_dynamic_users():
        print_error(
            _("pikaur requires systemd >= 235 (dynamic users) to be run as root."),
        )
        sys.exit(65)
    if not dep_names:
        dep_names = [
            "fakeroot",
        ] + (['sudo'] if not running_as_root() else [])
    for dep_bin in dep_names:
        if not shutil.which(dep_bin):
            print_error("'{}' {}.".format(
                bold_line(dep_bin),
                "executable not found"
            ))
            sys.exit(2)


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


def handle_sig_int(*_whatever) -> NoReturn:  # pragma: no cover
    print_stderr("\n\nCanceled by user (SIGINT)", lock=False)
    raise SysExit(125)


def main() -> None:
    try:
        args = parse_args()
    except ArgumentError as exc:
        print_stderr(exc)
        sys.exit(22)
    check_runtime_deps()

    create_dirs()
    # initialize config to avoid race condition in threads:
    PikaurConfig.get_config()

    atexit.register(restore_tty)
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    if not args.verbose:
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
