""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import codecs
import enum
import os
import shutil
import subprocess
import tempfile
from multiprocessing.pool import ThreadPool
from time import sleep
from typing import (
    TYPE_CHECKING,
    Any, Callable, Iterable, List, Optional, Union, Tuple,
)

import pyalpm

from .config import PikaurConfig
from .args import parse_args
from .pprint import print_stderr, color_line

if TYPE_CHECKING:
    # pylint: disable=unused-import,cyclic-import
    from .aur import AURPackageInfo  # noqa


NOT_FOUND_ATOM = object()


class ComparableType:

    __ignore_in_eq__: Tuple[str, ...] = tuple()

    def _key_not_exists(self, key):
        return getattr(self, key, NOT_FOUND_ATOM) is NOT_FOUND_ATOM

    __hash__ = object.__hash__

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            raise TypeError(f'{other} is not an instance of {self.__class__}')
        if not self.__ignore_in_eq__:
            return super().__eq__(other)
        self_vars = {}
        self_vars.update(vars(self))
        other_vars = {}
        other_vars.update(vars(other))
        for var_dict in (self_vars, other_vars):
            for skip_prop in self.__ignore_in_eq__:
                if skip_prop in var_dict:
                    del var_dict[skip_prop]
        return self_vars == other_vars


class DataType(ComparableType):

    def __init__(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)
        for key in self.__annotations__:  # pylint: disable=no-member
            if self._key_not_exists(key):
                raise TypeError(
                    f"'{self.__class__.__name__}' does "
                    f"not have required attribute '{key}' set"
                )

    def __setattr__(self, key: str, value: Any) -> None:
        if (
                not getattr(self, "__annotations__", None) or
                self.__annotations__.get(key, NOT_FOUND_ATOM) is NOT_FOUND_ATOM  # pylint: disable=no-member
        ) and self._key_not_exists(key):
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
                    color_line('=> ', 14) +
                    ' '.join(str(arg) for arg in self.args)
                )

        stdout, stderr = super().communicate(_input, _timeout)
        self.stdout_text = stdout.decode('utf-8') if stdout else None
        self.stderr_text = stderr.decode('utf-8') if stderr else None
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
            proc.stdout_text = out_file.read().decode('utf-8')
            proc.stderr_text = err_file.read().decode('utf-8')
    return proc


def joined_spawn(cmd: List[str], **kwargs) -> InteractiveSpawn:
    with tempfile.TemporaryFile() as out_file:
        proc = interactive_spawn(cmd, stdout=out_file, stderr=out_file, **kwargs)
        out_file.seek(0)
        proc.stdout_text = out_file.read().decode('utf-8')
    return proc


def running_as_root() -> bool:
    return os.geteuid() == 0


def isolate_root_cmd(cmd: List[str], cwd=None) -> List[str]:
    if not running_as_root():
        return cmd
    base_root_isolator = [
        'systemd-run',
        '--service-type=oneshot',
        '--pipe', '--wait', '--pty',
        '-p', 'DynamicUser=yes',
        '-p', 'CacheDirectory=pikaur',
        '-E', 'HOME=/tmp',
    ]
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
        return "utf8"

    # Python automatically detects endianess if utf-16 bom is present
    # write endianess generally determined by endianess of CPU
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
            raise catched_exc  # pylint: disable=raising-bad-type
        if result:
            return result
        return None
