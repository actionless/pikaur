"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import codecs
import datetime
import enum
import os
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from multiprocessing.pool import ThreadPool
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING

import pyalpm

from .args import parse_args
from .config import _USER_TEMP_ROOT, RUNNING_AS_ROOT, PikaurConfig
from .i18n import translate
from .pprint import ColorsHighlight, bold_line, color_line, print_error, print_stderr

if TYPE_CHECKING:
    # pylint: disable=cyclic-import
    from collections.abc import Callable, Sequence
    from typing import IO, Any, Final, TypeVar

    from typing_extensions import NotRequired, TypedDict

    from .aur import AURPackageInfo

    IOStream = IO[bytes] | int | None
    SudoLoopResultT = TypeVar("SudoLoopResultT")

    class SpawnArgs(TypedDict):
        stdout: NotRequired["IOStream"]
        stderr: NotRequired["IOStream"]
        cwd: NotRequired[str]
        env: NotRequired[dict[str, str]]


DEFAULT_INPUT_ENCODING: "Final" = "utf-8"
DEFAULT_TIMEZONE: "Final" = datetime.datetime.now().astimezone().tzinfo
PIPE: "Final" = subprocess.PIPE
SYSTEMD_MIN_VERSION: "Final" = 235
READ_MODE: "Final" = "r"


class ComparableType:

    __ignore_in_eq__: tuple[str, ...] = ()

    __hash__ = object.__hash__
    __compare_stack__: list["ComparableType"] | None = None

    @property
    def public_values(self) -> dict[str, "Any"]:
        return {
            var: val for var, val in vars(self).items()
            if not var.startswith("__")
        }

    def __eq__(self, other: "ComparableType") -> bool:  # type: ignore[override]
        if not isinstance(other, self.__class__):
            return False
        if not self.__compare_stack__:
            self.__compare_stack__ = []
        elif other in self.__compare_stack__:
            return super().__eq__(other)
        self.__compare_stack__.append(other)
        self_values = {}
        self_values.update(self.public_values)
        others_values = {}
        others_values.update(other.public_values)
        for values in (self_values, others_values):
            for skip_prop in self.__ignore_in_eq__:
                if skip_prop in values:
                    del values[skip_prop]
        result = self_values == others_values
        self.__compare_stack__ = None
        return result


class DataType(ComparableType):

    ignore_extra_properties: bool

    @property
    def __all_annotations__(self) -> dict[str, type]:
        annotations: dict[str, type] = {}
        for parent_class in reversed(self.__class__.mro()):
            annotations.update(**getattr(parent_class, "__annotations__", {}))
        return annotations

    def _key_exists(self, key: str) -> bool:
        return key in dir(self)

    def __init__(self, *, ignore_extra_properties: bool = False, **kwargs: "Any") -> None:
        self.ignore_extra_properties = ignore_extra_properties
        for key, value in kwargs.items():
            setattr(self, key, value)
        for key in self.__all_annotations__:
            if not self._key_exists(key):
                missing_required_attribute = translate(
                    "'{class_name}' does not have required attribute '{key}' set.",
                ).format(
                    class_name=self.__class__.__name__, key=key,
                )
                raise TypeError(missing_required_attribute)

    def __setattr__(self, key: str, value: "Any") -> None:
        if not (
            (
                key in self.__all_annotations__
            ) or self._key_exists(key)
        ):
            unknown_attribute = translate(
                "'{class_name}' does not have attribute '{key}' defined.",
            ).format(
                class_name=self.__class__.__name__, key=key,
            )
            if self.ignore_extra_properties:
                print_error(unknown_attribute)
            else:
                raise TypeError(unknown_attribute)
        super().__setattr__(key, value)


class PackageSource(enum.Enum):
    REPO = enum.auto()
    AUR = enum.auto()
    LOCAL = enum.auto()


class InstallInfo(DataType):
    name: str
    current_version: str
    new_version: str
    description: str | None = None
    maintainer: str | None = None
    repository: str | None = None
    devel_pkg_age_days: int | None = None
    package: "pyalpm.Package | AURPackageInfo"
    provided_by: list["pyalpm.Package | AURPackageInfo"] | None = None
    required_by: list["InstallInfo"] | None = None
    members_of: list[str] | None = None
    replaces: list[str] | None = None
    pkgbuild_path: str | None = None

    __ignore_in_eq__ = ("package", "provided_by", "pkgbuild_path")

    @property
    def package_source(self) -> PackageSource:
        if isinstance(self.package, pyalpm.Package):
            return PackageSource.REPO
        return PackageSource.AUR

    def __repr__(self) -> str:
        return (
            f'<{self.__class__.__name__} "{self.name}" '
            f"{self.current_version} -> {self.new_version}>"
        )


class RepoInstallInfo(InstallInfo):
    package: "pyalpm.Package"


class AURInstallInfo(InstallInfo):
    package: "AURPackageInfo"


def sudo(cmd: list[str]) -> list[str]:
    if running_as_root():
        return cmd
    return [PikaurConfig().misc.PrivilegeEscalationTool.get_str(), *cmd]


def get_sudo_refresh_command() -> list[str]:
    pacman_path = PikaurConfig().misc.PacmanPath.get_str()
    return sudo([pacman_path, "-T"])


class InteractiveSpawn(subprocess.Popen[bytes]):

    stdout_text: str | None
    stderr_text: str | None
    _terminated: bool = False

    def communicate(
            self, com_input: bytes | None = None, timeout: float | None = None,
    ) -> tuple[bytes, bytes]:
        if (
                parse_args().print_commands
                and not self._terminated
                and self.args != get_sudo_refresh_command()
        ):
            print_stderr(
                color_line("=> ", ColorsHighlight.cyan) +
                (
                    " ".join(str(arg) for arg in self.args)
                    if isinstance(self.args, list) else
                    str(self.args)
                ),
                lock=False,
            )

        stdout, stderr = super().communicate(com_input, timeout)
        self.stdout_text = stdout.decode(DEFAULT_INPUT_ENCODING) if stdout else None
        self.stderr_text = stderr.decode(DEFAULT_INPUT_ENCODING) if stderr else None
        return stdout, stderr

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__} returned {self.returncode}:\n"
            f"STDOUT:\n{self.stdout_text}\n\n"
            f"STDERR:\n{self.stderr_text}"
        )

    def __del__(self) -> None:
        self.terminate()
        self._terminated = True
        self.communicate()


def interactive_spawn(
        cmd: list[str],
        stdout: "IOStream | None" = None,
        stderr: "IOStream | None" = None,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
) -> InteractiveSpawn:
    kwargs: "SpawnArgs" = {}
    if stdout:
        kwargs["stdout"] = stdout
    if stderr:
        kwargs["stderr"] = stderr
    if cwd:
        kwargs["cwd"] = str(cwd)
    if env:
        kwargs["env"] = env
    process = InteractiveSpawn(
        cmd, **kwargs,
    )
    process.communicate()
    return process


def spawn(
        cmd: list[str],
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
) -> InteractiveSpawn:
    with (
            tempfile.TemporaryFile() as out_file,
            tempfile.TemporaryFile() as err_file,
    ):
        proc = interactive_spawn(
            cmd, stdout=out_file, stderr=err_file,
            cwd=cwd, env=env,
        )
        out_file.seek(0)
        err_file.seek(0)
        proc.stdout_text = out_file.read().decode(DEFAULT_INPUT_ENCODING)
        proc.stderr_text = err_file.read().decode(DEFAULT_INPUT_ENCODING)
    return proc


def joined_spawn(
        cmd: list[str],
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
) -> InteractiveSpawn:
    with tempfile.TemporaryFile() as out_file:
        proc = interactive_spawn(
            cmd, stdout=out_file, stderr=out_file,
            cwd=cwd, env=env,
        )
        out_file.seek(0)
        proc.stdout_text = out_file.read().decode(DEFAULT_INPUT_ENCODING)
    return proc


def running_as_root() -> bool:
    return RUNNING_AS_ROOT


def isolate_root_cmd(
        cmd: list[str],
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
) -> list[str]:
    if not running_as_root():
        return cmd
    if isinstance(cwd, str):
        cwd = Path(cwd)
    base_root_isolator = [
        "/usr/sbin/systemd-run",
        "--service-type=oneshot",
        "--pipe", "--wait", "--pty",
        "-p", "DynamicUser=yes",
        "-p", "CacheDirectory=pikaur",
        "-E", f"HOME={_USER_TEMP_ROOT}",
    ]
    if env is not None:
        for env_var_name, env_var_value in env.items():
            base_root_isolator += ["-E", f"{env_var_name}={env_var_value}"]
    if cwd is not None:
        base_root_isolator += ["-p", "WorkingDirectory=" + str(cwd.resolve())]
    for env_var_name in (
            "http_proxy", "https_proxy", "ftp_proxy",
    ):
        if os.environ.get(env_var_name) is not None:
            base_root_isolator += ["-E", f"{env_var_name}={os.environ[env_var_name]}"]
    return base_root_isolator + cmd


class CodepageSequences:
    UTF_8: "Final[Sequence[bytes]]" = (b"\xef\xbb\xbf", )
    UTF_16: "Final[Sequence[bytes]]" = (b"\xfe\xff", b"\xff\xfe")
    UTF_32: "Final[Sequence[bytes]]" = (b"\xfe\xff\x00\x00", b"\x00\x00\xff\xfe")


def detect_bom_type(file_path: str | Path) -> str:
    """
    returns file encoding string for open() function
    https://stackoverflow.com/a/44295590/1850190
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)
    with file_path.open("rb") as test_file:
        first_bytes = test_file.read(4)

    if first_bytes[0:3] in CodepageSequences.UTF_8:
        return "utf-8"

    # Python automatically detects endianness if utf-16 bom is present
    # write endianness generally determined by endianness of CPU
    if first_bytes[0:2] in CodepageSequences.UTF_16:
        return "utf16"

    if first_bytes[0:5] in CodepageSequences.UTF_32:
        return "utf32"

    # If BOM is not provided, then assume its the codepage
    #     used by your operating system
    return "cp1252"
    # For the United States its: cp1252


def open_file(
        file_path: str | Path, mode: str = READ_MODE, encoding: str | None = None,
) -> codecs.StreamReaderWriter:
    if encoding is None and (mode and READ_MODE in mode):
        encoding = detect_bom_type(file_path)
    if encoding:
        return codecs.open(
            str(file_path), mode, errors="ignore", encoding=encoding,
        )
    return codecs.open(
        str(file_path), mode, errors="ignore",
    )


def replace_file(src: str | Path, dest: str | Path) -> None:
    if isinstance(src, str):
        src = Path(src)
    if isinstance(dest, str):
        dest = Path(dest)
    if src.exists():
        if dest.exists():
            dest.unlink()
        shutil.move(src, dest)


def remove_dir(dir_path: str | Path) -> None:
    try:
        shutil.rmtree(dir_path)
    except PermissionError:
        interactive_spawn(sudo(["rm", "-rf", str(dir_path)]))


def get_editor() -> list[str] | None:
    editor_line = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor_line:
        return editor_line.split(" ")
    for editor in (
            "vim", "nano", "mcedit", "edit", "emacs", "nvim", "kak",
            "e3", "atom", "adie", "dedit", "gedit", "jedit", "kate", "kwrite", "leafpad",
            "mousepad", "notepadqq", "pluma", "code", "xed", "nvim-qt", "geany",
    ):
        path = shutil.which(editor)
        if path:
            return [path]
    return None


def dirname(path: str | Path) -> Path:
    return Path(path).parent if path else Path(".")


def sudo_loop(*, once: bool = False) -> None:
    """Get sudo for further questions."""
    sudo_loop_interval = PikaurConfig().misc.SudoLoopInterval.get_int()
    if sudo_loop_interval == -1:
        return
    while True:
        interactive_spawn(get_sudo_refresh_command())
        if once:
            break
        sleep(sudo_loop_interval)


def run_with_sudo_loop(function: "Callable[..., SudoLoopResultT]") -> "SudoLoopResultT | None":
    sudo_loop(once=True)
    with ThreadPool(processes=2) as pool:
        main_thread = pool.apply_async(function, ())
        pool.apply_async(sudo_loop)
        pool.close()
        catched_exc: Exception | None = None
        result: "SudoLoopResultT | None" = None
        try:
            result = main_thread.get()
        except Exception as exc:
            catched_exc = exc
        finally:
            pool.terminate()
        if catched_exc:
            raise catched_exc
        return result


def check_systemd_dynamic_users() -> bool:  # pragma: no cover
    try:
        out = subprocess.check_output(
            ["/usr/sbin/systemd-run", "--version"],  # nosec B603  # noqa: S603
            universal_newlines=True,
        )
    except FileNotFoundError:
        return False
    first_line = out.split("\n", maxsplit=1)[0]
    version = int(first_line.split(maxsplit=2)[1])
    return version >= SYSTEMD_MIN_VERSION


def check_runtime_deps(dep_names: list[str] | None = None) -> None:
    if sys.version_info < (3, 7):
        print_error(
            translate("pikaur requires Python >= 3.7 to run."),
        )
        sys.exit(65)
    if running_as_root() and not check_systemd_dynamic_users():
        print_error(
            translate("pikaur requires systemd >= 235 (dynamic users) to be run as root."),
        )
        sys.exit(65)
    if not dep_names:
        privilege_escalation_tool = PikaurConfig().misc.PrivilegeEscalationTool.get_str()
        dep_names = ["fakeroot"] + (
            [privilege_escalation_tool] if not running_as_root() else []
        )

    for dep_bin in dep_names:
        if not shutil.which(dep_bin):
            print_error("'{}' {}.".format(  # pylint: disable=consider-using-f-string
                bold_line(dep_bin),
                translate("executable not found"),
            ))
            sys.exit(2)
