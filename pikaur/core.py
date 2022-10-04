""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import codecs
import enum
import os
import shutil
import subprocess
import tempfile
import sys
from multiprocessing.pool import ThreadPool
from time import sleep
from typing import (
    TYPE_CHECKING,
    Any, Callable, Iterable, List, Optional, Union, Tuple, Dict,
)

import pyalpm

from .args import parse_args
from .config import PikaurConfig
from .i18n import translate
from .pprint import (
    print_stderr, color_line, print_error, bold_line, ColorsHighlight,
)

if TYPE_CHECKING:
    # pylint: disable=cyclic-import
    from .aur import AURPackageInfo  # noqa


DEFAULT_INPUT_ENCODING = 'utf-8'


class ComparableType:

    __ignore_in_eq__: Tuple[str, ...] = tuple()

    __hash__ = object.__hash__
    __compare_stack__: Optional[List[Any]] = None

    @property
    def public_vars(self):
        return {
            var: val for var, val in vars(self).items()
            if not var.startswith('__')
        }

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        if not self.__compare_stack__:
            self.__compare_stack__ = []
        elif other in self.__compare_stack__:
            return super().__eq__(other)
        self.__compare_stack__.append(other)
        self_vars = {}
        self_vars.update(self.public_vars)
        other_vars = {}
        other_vars.update(other.public_vars)
        for var_dict in (self_vars, other_vars):
            for skip_prop in self.__ignore_in_eq__:
                if skip_prop in var_dict:
                    del var_dict[skip_prop]
        result = self_vars == other_vars
        self.__compare_stack__ = None
        return result


class DataType(ComparableType):

    @classmethod  # type: ignore[misc]
    @property
    def __all_annotations__(cls) -> Dict[str, Any]:
        annotations: Dict[str, Any] = {}
        for parent_class in reversed(cls.mro()):
            annotations.update(**getattr(parent_class, '__annotations__', {}))
        return annotations

    def _key_exists(self, key: str) -> bool:
        return key in dir(self)

    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)
        for key in self.__all_annotations__:
            if not self._key_exists(key):
                raise TypeError(
                    f"'{self.__class__.__name__}' does "
                    f"not have required attribute '{key}' set"
                )

    def __setattr__(self, key: str, value: Any) -> None:
        if not (
            (
                key in self.__all_annotations__
            ) or self._key_exists(key)
        ):
            raise TypeError(
                f"'{self.__class__.__name__}' does "
                f"not have attribute '{key}'"
            )
        super().__setattr__(key, value)


class PackageSource(enum.Enum):
    REPO = enum.auto()
    AUR = enum.auto()
    LOCAL = enum.auto()


class InstallInfo(DataType):
    name: str
    current_version: str
    new_version: str
    description: Optional[str] = None
    maintainer: Optional[str] = None
    repository: Optional[str] = None
    devel_pkg_age_days: Optional[int] = None
    package: Union['pyalpm.Package', 'AURPackageInfo']
    provided_by: Optional[List[Union['pyalpm.Package', 'AURPackageInfo']]] = None
    required_by: Optional[List['InstallInfo']] = None
    members_of: Optional[List[str]] = None
    replaces: Optional[List[str]] = None
    pkgbuild_path: Optional[str] = None

    __ignore_in_eq__ = ('package', 'provided_by', 'pkgbuild_path')

    @property
    def package_source(self) -> PackageSource:
        if isinstance(self.package, pyalpm.Package):
            return PackageSource.REPO
        return PackageSource.AUR

    def __repr__(self) -> str:
        return (
            f'<{self.__class__.__name__} "{self.name}" '
            f'{self.current_version} -> {self.new_version}>'
        )


class RepoInstallInfo(InstallInfo):
    package: 'pyalpm.Package'


class AURInstallInfo(InstallInfo):
    package: 'AURPackageInfo'


def sudo(cmd: List[str]) -> List[str]:
    if running_as_root():
        return cmd
    return [PikaurConfig().misc.PrivilegeEscalationTool.get_str(), ] + cmd


def get_sudo_refresh_command() -> List[str]:
    pacman_path = PikaurConfig().misc.PacmanPath.get_str()
    return sudo([pacman_path, '-T'])


class InteractiveSpawn(subprocess.Popen):

    stdout_text: str
    stderr_text: str

    def communicate(self, _input=None, _timeout=None) -> Tuple[bytes, bytes]:
        if parse_args().print_commands:
            if self.args != get_sudo_refresh_command():
                print_stderr(
                    color_line('=> ', ColorsHighlight.cyan) +
                    (
                        ' '.join(str(arg) for arg in self.args)
                        if isinstance(self.args, list) else
                        str(self.args)
                    )
                )

        stdout, stderr = super().communicate(_input, _timeout)
        self.stdout_text = stdout.decode(DEFAULT_INPUT_ENCODING) if stdout else None
        self.stderr_text = stderr.decode(DEFAULT_INPUT_ENCODING) if stderr else None
        return stdout, stderr

    def __repr__(self) -> str:
        return (
            f'{self.__class__.__name__} returned {self.returncode}:\n'
            f'STDOUT:\n{self.stdout_text}\n\n'
            f'STDERR:\n{self.stderr_text}'
        )


def interactive_spawn(cmd: List[str], **kwargs) -> InteractiveSpawn:
    process = InteractiveSpawn(cmd, **kwargs)
    process.communicate()
    return process


def spawn(cmd: List[str], **kwargs) -> InteractiveSpawn:
    with tempfile.TemporaryFile() as out_file:
        with tempfile.TemporaryFile() as err_file:
            proc = interactive_spawn(cmd, stdout=out_file, stderr=err_file, **kwargs)
            out_file.seek(0)
            err_file.seek(0)
            proc.stdout_text = out_file.read().decode(DEFAULT_INPUT_ENCODING)
            proc.stderr_text = err_file.read().decode(DEFAULT_INPUT_ENCODING)
    return proc


def joined_spawn(cmd: List[str], **kwargs) -> InteractiveSpawn:
    with tempfile.TemporaryFile() as out_file:
        proc = interactive_spawn(cmd, stdout=out_file, stderr=out_file, **kwargs)
        out_file.seek(0)
        proc.stdout_text = out_file.read().decode(DEFAULT_INPUT_ENCODING)
    return proc


def running_as_root() -> bool:
    return os.geteuid() == 0


def isolate_root_cmd(cmd: List[str], cwd=None, env=None) -> List[str]:
    if not running_as_root():
        return cmd
    base_root_isolator = [
        '/usr/sbin/systemd-run',
        '--service-type=oneshot',
        '--pipe', '--wait', '--pty',
        '-p', 'DynamicUser=yes',
        '-p', 'CacheDirectory=pikaur',
        '-E', 'HOME=/tmp',
    ]
    if env is not None:
        for env_var_name, env_var_value in env.items():
            base_root_isolator += ['-E', f'{env_var_name}={env_var_value}']
    if cwd is not None:
        base_root_isolator += ['-p', 'WorkingDirectory=' + os.path.abspath(cwd)]
    for env_var_name in (
            'http_proxy', 'https_proxy', 'ftp_proxy',
    ):
        if os.environ.get(env_var_name) is not None:
            base_root_isolator += ['-E', f'{env_var_name}={os.environ[env_var_name]}']
    return base_root_isolator + cmd


def detect_bom_type(file_path: str) -> str:
    """
    returns file encoding string for open() function
    https://stackoverflow.com/a/44295590/1850190
    """

    with open(file_path, 'rb') as test_file:
        first_bytes = test_file.read(4)

    if first_bytes[0:3] == b'\xef\xbb\xbf':
        return "utf-8"

    # Python automatically detects endianness if utf-16 bom is present
    # write endianness generally determined by endianness of CPU
    if (
            first_bytes[0:2] == b'\xfe\xff'
    ) or (
        first_bytes[0:2] == b'\xff\xfe'
    ):
        return "utf16"

    if (
            first_bytes[0:5] == b'\xfe\xff\x00\x00'
    ) or (
        first_bytes[0:5] == b'\x00\x00\xff\xfe'
    ):
        return "utf32"

    # If BOM is not provided, then assume its the codepage
    #     used by your operating system
    return "cp1252"
    # For the United States its: cp1252


def open_file(
        file_path: str, mode='r', encoding: str = None, **kwargs
) -> codecs.StreamReaderWriter:
    if encoding is None and (mode and 'r' in mode):
        encoding = detect_bom_type(file_path)
    if encoding:
        kwargs['encoding'] = encoding
    return codecs.open(
        file_path, mode, errors='ignore', **kwargs
    )


def replace_file(src: str, dest: str) -> None:
    if os.path.exists(src):
        if os.path.exists(dest):
            os.remove(dest)
        shutil.move(src, dest)


def remove_dir(dir_path: str) -> None:
    try:
        shutil.rmtree(dir_path)
    except PermissionError:
        interactive_spawn(sudo(['rm', '-rf', dir_path]))


def get_chunks(iterable: Iterable[Any], chunk_size: int) -> Iterable[List[Any]]:
    result = []
    index = 0
    for item in iterable:
        result.append(item)
        index += 1
        if index == chunk_size:
            yield result
            result = []
            index = 0
    if result:
        yield result


def get_editor() -> Optional[List[str]]:
    editor_line = os.environ.get('VISUAL') or os.environ.get('EDITOR')
    if editor_line:
        return editor_line.split(' ')
    for editor in (
            'vim', 'nano', 'mcedit', 'edit', 'emacs', 'nvim', 'kak',
            'e3', 'atom', 'adie', 'dedit', 'gedit', 'jedit', 'kate', 'kwrite', 'leafpad',
            'mousepad', 'notepadqq', 'pluma', 'code', 'xed', 'nvim-qt', 'geany',
    ):
        path = shutil.which(editor)
        if path:
            return [path, ]
    return None


def dirname(path: str) -> str:
    return os.path.dirname(path) or '.'


def sudo_loop(once=False) -> None:
    """
    get sudo for further questions
    """
    sudo_loop_interval = PikaurConfig().misc.SudoLoopInterval.get_int()
    if sudo_loop_interval == -1:
        return
    while True:
        interactive_spawn(get_sudo_refresh_command())
        if once:
            break
        sleep(sudo_loop_interval)


def run_with_sudo_loop(function: Callable) -> Optional[Any]:
    sudo_loop(once=True)
    with ThreadPool(processes=2) as pool:
        main_thread = pool.apply_async(function, ())
        pool.apply_async(sudo_loop)
        pool.close()
        catched_exc = None
        result: Optional[Any] = None
        try:
            result = main_thread.get()
        except Exception as exc:
            catched_exc = exc
        finally:
            pool.terminate()
        if catched_exc:
            raise catched_exc
        if result:
            return result
        return None


def check_systemd_dynamic_users() -> bool:  # pragma: no cover
    try:
        out = subprocess.check_output(['/usr/sbin/systemd-run', '--version'],  # nosec B603
                                      universal_newlines=True)
    except FileNotFoundError:
        return False
    first_line = out.split('\n', maxsplit=1)[0]
    version = int(first_line.split(maxsplit=2)[1])
    return version >= 235


def check_runtime_deps(dep_names: Optional[List[str]] = None) -> None:
    if sys.version_info.major < 3 or sys.version_info.minor < 7:
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
        dep_names = ["fakeroot", ] + (
            [privilege_escalation_tool] if not running_as_root() else []
        )

    for dep_bin in dep_names:
        if not shutil.which(dep_bin):
            print_error("'{}' {}.".format(  # pylint: disable=consider-using-f-string
                bold_line(dep_bin),
                translate("executable not found")
            ))
            sys.exit(2)
