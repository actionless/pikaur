"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import atexit
import io
import os
import readline
import shutil
import signal
import sys
import traceback
from argparse import ArgumentError
from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING

import pyalpm

from .args import parse_args
from .config import (
    DEFAULT_INPUT_ENCODING,
    AurReposCachePath,
    CacheRoot,
    DataRoot,
    PikaurConfig,
    RunningAsRoot,
    UsingDynamicUsers,
    _OldAurReposCachePath,
    _UserCacheRoot,
)
from .exceptions import SysExit
from .getpkgbuild_cli import cli_getpkgbuild
from .help_cli import cli_print_help
from .i18n import translate
from .info_cli import cli_info_packages
from .install_cli import InstallPackagesCLI
from .logging_extras import create_logger
from .os_utils import (
    check_executables,
    mkdir,
)
from .pacman import PackageDB
from .pikaprint import TTYRestore, bold_line, print_error, print_stderr, print_warning
from .pikatypes import AURPackageInfo
from .pikspect import PikspectSignalHandler
from .pkg_cache_cli import cli_clean_packages_cache
from .print_department import print_version
from .privilege import (
    get_args_to_elevate_pikaur,
    isolate_root_cmd,
    need_dynamic_users,
    sudo,
)
from .prompt import NotANumberInputError, get_multiple_numbers_input
from .search_cli import cli_search_packages, search_packages
from .spawn import (
    interactive_spawn,
    spawn,
)
from .updates import print_upgradeable
from .urllib_helper import ProxyInitSocks5Error, init_proxy
from .version import split_version

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import FrameType
    from typing import Any, Final


def init_readline() -> None:
    # follow GNU readline config in prompts:
    system_inputrc_path = Path("/etc/inputrc")
    if system_inputrc_path.exists():
        readline.read_init_file(system_inputrc_path)
    user_inputrc_path = Path("~/.inputrc").expanduser()
    if user_inputrc_path.exists():
        readline.read_init_file(user_inputrc_path)


init_readline()

SYSTEMD_MIN_VERSION: "Final" = 235
logger = create_logger(f"main_{os.getuid()}")


# @TODO: use arg to enable it
FILE_DEBUG: "Final" = False


def file_debug(message: "Any") -> None:
    if FILE_DEBUG:
        with Path("./pikaur_debug_main.txt").open("a", encoding=DEFAULT_INPUT_ENCODING) as fobj:
            fobj.write(str(message) + "\n")


class OutputEncodingWrapper(AbstractContextManager[None]):

    original_stderr: int
    original_stdout: int

    def __enter__(self) -> None:
        for attr in ("stdout", "stderr"):
            logger.debug(
                "Setting {} to {}...", attr, DEFAULT_INPUT_ENCODING,
                lock=False,
            )
            real_stream = getattr(sys, attr)
            if real_stream.encoding == DEFAULT_INPUT_ENCODING:
                logger.debug("already set - nothing to do", lock=False)
                continue
            real_stream.flush()
            try:
                setattr(
                    self, f"original_{attr}",
                    real_stream,
                )
                setattr(
                    sys, attr,
                    open(
                        real_stream.fileno(),
                        mode="w",
                        encoding=DEFAULT_INPUT_ENCODING,
                        closefd=False,
                    ),
                )
            except io.UnsupportedOperation as exc:
                logger.debug(
                    "Can't set {} to {}:\n{}",
                    attr, DEFAULT_INPUT_ENCODING, exc,
                    lock=False,
                )

    def __exit__(
            self,
            exc_class: type[BaseException] | None,
            exc_instance: BaseException | None,
            exc_tb: TracebackType | None,
    ) -> None:
        try:
            # @TODO: replace all SysExit-s to SystemExit-s eventually :3
            if exc_instance and exc_class and (exc_class not in {SysExit, SystemExit}):
                # handling exception in context manager's __exit__ is not recommended
                # but otherwise stderr would be closed before exception is printed...
                if exc_tb:
                    print_stderr("".join(traceback.format_tb(exc_tb)), lock=False)
                print_stderr(f"{exc_class.__name__}: {exc_instance}", lock=False)
                sys.exit(121)
        finally:
            for attr in ("stdout", "stderr"):
                logger.debug("Restoring {}...", attr, lock=False)
                stream = getattr(sys, attr)
                orig_stream = getattr(self, f"original_{attr}", None)
                if orig_stream in {None, stream}:
                    logger.debug("nothing to do", lock=False)
                    continue
                stream.flush()
                setattr(
                    sys, attr,
                    orig_stream,
                )
                logger.debug("{} restored", attr, lock=False)
                stream.close()
                logger.debug("closed old {} stream", attr, lock=False)


def cli_print_upgradeable() -> None:
    print_upgradeable()


def cli_install_packages() -> None:
    InstallPackagesCLI()


def cli_pkgbuild() -> None:
    cli_install_packages()


def cli_print_version() -> None:
    args = parse_args()
    proc = spawn([
        PikaurConfig().misc.PacmanPath.get_str(), "--version",
    ])
    pacman_version = proc.stdout_text.splitlines()[1].strip(" .-") if proc.stdout_text else "N/A"
    print_version(
        pacman_version=pacman_version, pyalpm_version=pyalpm.version(),
        quiet=args.quiet,
    )


def cli_dynamic_select() -> None:  # pragma: no cover
    packages = search_packages(enumerated=True)
    if not packages:
        raise SysExit(1)

    while True:
        try:
            print_stderr(
                "\n" + translate(
                    "Please enter the number of the package(s) you want to install "
                    "and press [Enter] (default={}):",
                ).format(1),
            )
            answers = get_multiple_numbers_input(answers=list(range(1, len(packages) + 1))) or [1]
            print_stderr()
            selected_pkgs_idx = [idx - 1 for idx in answers]
            restart_prompt = False
            for idx in selected_pkgs_idx:
                if not 0 <= idx < len(packages):
                    print_error(translate("invalid value: {} is not between {} and {}").format(
                        idx + 1, 1, len(packages),
                    ))
                    restart_prompt = True
            if restart_prompt:
                continue
            break
        except NotANumberInputError as exc:
            if exc.character.lower() == translate("n"):
                raise SysExit(128) from exc
            print_error(translate("invalid number: {}").format(exc.character))

    new_args = [*sys.argv]
    for positional in parse_args().positional:
        new_args.remove(positional)
    new_args += ["--sync"]
    for idx in selected_pkgs_idx:
        pkg = packages[idx]
        repo = "aur" if isinstance(pkg, AURPackageInfo) else pkg.db.name
        new_args += [f"{repo}/{pkg.name}"]
    execute_pikaur_operation(
        pikaur_operation=cli_install_packages,
        require_sudo=True,
        replace_args=new_args,
    )


def execute_pikaur_operation(
        pikaur_operation: "Callable[[], None]",
        *,
        require_sudo: bool,
        replace_args: None | list[str] = None,
) -> None:
    args = parse_args()
    cli_args = replace_args or sys.argv
    logger.debug("Pikaur operation found for args {}: {}", cli_args, pikaur_operation.__name__)
    if args.read_stdin:
        logger.debug("Handling stdin as positional args:")
        logger.debug("    {}", args.positional)
        add_args = [
            word
            for line in sys.stdin.readlines()
            for word in line.split()
        ]
        logger.debug("    {}", add_args)
        args.positional += add_args
        cli_args += add_args
    if (
            RunningAsRoot()
            and (PikaurConfig().build.DynamicUsers.get_str() == "never" and not args.user_id)
    ):
        print_error(
            translate(
                "Either SystemD Dynamic Users must be enabled"
                " or User ID should be set if running as root.",
            ),
        )
        sys.exit(1)
    elif (
            require_sudo
            and not RunningAsRoot()
            and (
                args.privilege_escalation_target == "pikaur"
                or need_dynamic_users()
            )
    ):
        # Restart pikaur with sudo to use systemd dynamic users or current user id
        sys.exit(interactive_spawn(
            get_args_to_elevate_pikaur(cli_args),
        ).returncode)
    else:
        # Just run the operation normally
        pikaur_operation()


def cli_entry_point() -> None:
    # pylint: disable=too-many-branches

    try:
        init_proxy()
    except ProxyInitSocks5Error as exc:
        print_error("".join(exc.args))
        sys.exit(2)

    # operations are parsed in order what the less destructive (like info and query)
    # are being handled first, for cases when user by mistake
    # specified both operations, like `pikaur -QS smth`

    args = parse_args()
    pikaur_operation: Callable[[], None] | None = None
    require_sudo = False

    if args.help:
        pikaur_operation = cli_print_help

    elif args.version:
        pikaur_operation = cli_print_version

    elif args.query:
        if args.upgrades:
            pikaur_operation = cli_print_upgradeable

    elif args.files:
        require_sudo = bool(args.refresh)

    elif args.getpkgbuild:
        pikaur_operation = cli_getpkgbuild

    elif args.pkgbuild:
        require_sudo = True
        pikaur_operation = cli_pkgbuild

    elif args.sync:
        if args.search or args.list:
            pikaur_operation = cli_search_packages
        elif args.info:
            pikaur_operation = cli_info_packages
        elif args.clean:
            if not args.aur:
                require_sudo = True
            pikaur_operation = cli_clean_packages_cache
        elif args.groups:
            require_sudo = False
        else:
            require_sudo = True
            pikaur_operation = cli_install_packages

    elif args.interactive_package_select:
        pikaur_operation = cli_dynamic_select

    else:
        require_sudo = True

    if pikaur_operation:
        execute_pikaur_operation(pikaur_operation=pikaur_operation, require_sudo=require_sudo)
    else:
        # Just bypass all the args to pacman
        logger.debug("Pikaur operation not found for args: {}", sys.argv)
        logger.debug(args)
        pacman_args = [PikaurConfig().misc.PacmanPath.get_str(), *args.raw_without_pikaur_specific]
        if require_sudo:
            pacman_args = sudo(pacman_args)
        sys.exit(
            interactive_spawn(pacman_args).returncode,
        )


def migrate_old_aur_repos_dir() -> None:
    old_aur_repos_cache_path = _OldAurReposCachePath()
    new_aur_repos_cache_path = AurReposCachePath()
    if not (
            old_aur_repos_cache_path.exists() and not new_aur_repos_cache_path.exists()
    ):
        return
    mkdir(DataRoot())
    shutil.move(old_aur_repos_cache_path, new_aur_repos_cache_path)

    print_stderr()
    print_warning(
        translate(
            "AUR repos dir has been moved from '{old}' to '{new}'.",
        ).format(
            old=old_aur_repos_cache_path,
            new=new_aur_repos_cache_path,
        ),
    )
    print_stderr()


def create_dirs() -> None:
    if UsingDynamicUsers():
        # Let systemd-run setup the directories and symlinks
        true_cmd = isolate_root_cmd(["true"])
        result = spawn(true_cmd)
        if result.returncode != 0:
            raise RuntimeError(result)
        # Chown the private CacheDirectory to root to signal systemd that
        # it needs to recursively chown it to the correct user
        os.chown(os.path.realpath(CacheRoot()), 0, 0)
        mkdir(_UserCacheRoot())
    mkdir(CacheRoot())
    migrate_old_aur_repos_dir()
    mkdir(AurReposCachePath())


def restore_tty() -> None:
    TTYRestore.restore()


def create_handle_stop(reason: str = "SIGINT") -> "Callable[[int, FrameType | None], Any]":
    def handle_stop(sig: int, frame: "FrameType | None") -> None:  # pragma: no cover
        msg_started = f"\n\nCanceling by user ({reason})..."
        file_debug(msg_started)
        logger.debug(msg_started, lock=False)
        if signal_handler := PikspectSignalHandler.get():
            msg_custom = "\n\nFound Pikspect handler"
            file_debug(msg_custom)
            logger.debug(msg_custom, lock=False)
            signal_handler(sig, frame)  # pylint: disable=not-callable
            return
        if parse_args().pikaur_debug:
            raise KeyboardInterrupt
        print_stderr(f"\n\nCanceled by user ({reason})", lock=False)
        raise SysExit(125)
    return handle_stop


class EmptyWrapper:

    def __enter__(self) -> None:
        pass

    def __exit__(self, *_exc_details: object) -> None:
        pass


def check_systemd_dynamic_users_version() -> bool:  # pragma: no cover
    # @TODO: remove this check later as systemd v 235 is quite OLD already
    pkg = PackageDB.get_local_pkg_uncached("systemd")
    if not pkg:
        return False
    check_executables(["systemd-run"])
    version = int(split_version(pkg.version)[0])
    return version >= SYSTEMD_MIN_VERSION


def check_runtime_deps() -> None:
    if sys.version_info < (3, 7):
        print_error(
            translate("pikaur requires Python >= 3.7 to run."),
        )
        sys.exit(65)
    if (
        (PikaurConfig().build.DynamicUsers.get_str() != "never" and not parse_args().user_id)
        and (UsingDynamicUsers() and not check_systemd_dynamic_users_version())
    ):
        print_error(
            translate("pikaur requires systemd >= 235 (dynamic users) to be run as root."),
        )
        sys.exit(65)
    privilege_escalation_tool = PikaurConfig().misc.PrivilegeEscalationTool.get_str()
    if not PackageDB.get_local_pkg_uncached("base-devel"):
        warn_about_non_sudo \
            = PikaurConfig().ui.WarnAboutNonDefaultPrivilegeEscalationTool.get_bool()
        if warn_about_non_sudo or privilege_escalation_tool == "sudo":
            print_stderr()
            print_warning(
                "\n".join([
                    "",
                    translate(
                        "".join([  # grep -v grep 😸
                            chr(ord(c) - 1)
                            for c in
                            "Sfbe!ebno!bsdi.xjlj!cfgpsf!cpsljoh!zpvs!dpnqvufs;"
                        ]),
                    ),
                    bold_line(
                        "".join([
                            chr(ord(c) - 1)
                            for c in
                            "iuuqt;00xjlj/bsdimjovy/psh0ujumf0Bsdi`Vtfs`Sfqptjupsz"
                        ]),
                    ),
                    translate(
                        "".join([
                            chr(ord(c) - 1)
                            for c in
                            ")Bmtp-!epo(u!sfqpsu!boz!jttvft!up!qjlbvs-!jg!vsf!tffjoh!uijt!nfttbhf*"
                        ]),
                    ),
                    "",
                ] if privilege_escalation_tool == "sudo" else [
                    "",
                    translate(
                        "{privilege_escalation_tool} is not part of minimal Arch default setup,"
                        " be aware that you could run into potential problems.",
                    ).format(privilege_escalation_tool=privilege_escalation_tool),
                    "",
                ]),
            )
    if not RunningAsRoot():
        check_executables([privilege_escalation_tool])


def main(*, embed: bool = False) -> None:
    wrapper: type[AbstractContextManager[None]] = OutputEncodingWrapper
    TTYRestore.save()
    if embed:
        wrapper = EmptyWrapper
    with wrapper():
        try:
            parse_args()
        except ArgumentError as exc:
            print_stderr(exc)
            sys.exit(22)
        check_runtime_deps()

        # initialize config to avoid race condition in threads:
        PikaurConfig.get_config()

        create_dirs()

        atexit.register(restore_tty)
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        signal.signal(signal.SIGINT, create_handle_stop())
        signal.signal(signal.SIGTERM, create_handle_stop("SIGTERM"))

        try:
            cli_entry_point()
        except BrokenPipeError:
            # @TODO: should it be 32?
            sys.exit(0)
        except SysExit as exc:
            sys.exit(exc.code)
        sys.exit(0)


if __name__ == "__main__":
    main()
