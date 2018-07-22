""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import os
import shutil
import subprocess
import enum
import codecs
import tempfile
from typing import Any, List, Iterable, Callable, Optional, Union, TYPE_CHECKING

from .i18n import _
from .pprint import print_stderr, color_line

if TYPE_CHECKING:
    # pylint: disable=unused-import
    import pyalpm  # noqa
    from .aur import AURPackageInfo  # noqa


NOT_FOUND_ATOM = object()


class DataType():

    def __init__(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __setattr__(self, key: str, value: Any) -> None:
        if (
                not getattr(self, "__annotations__", None) or
                self.__annotations__.get(key, NOT_FOUND_ATOM) is NOT_FOUND_ATOM  # pylint: disable=no-member
        ) and (
            getattr(self, key, NOT_FOUND_ATOM) is NOT_FOUND_ATOM
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
    description: str
    repository: Optional[str] = None
    devel_pkg_age_days: Optional[int] = None
    package: Union['pyalpm.Package', 'AURPackageInfo']
    provided_by: Optional[List[Union['pyalpm.Package', 'AURPackageInfo']]] = None
    required_by: Optional[List['InstallInfo']] = None
    members_of: Optional[List[str]] = None
    replaces: Optional[List[str]] = None
    pkgbuild_path: Optional[str] = None

    def __repr__(self) -> str:
        return (
            f'<{self.__class__.__name__} "{self.name}" '
            f'{self.current_version} -> {self.new_version}>'
        )


class InteractiveSpawn(subprocess.Popen):

    stdout_text: str
    stderr_text: str

    def communicate(self, _input=None, _timeout=None):
        stdout, stderr = super().communicate(_input, _timeout)
        self.stdout_text = stdout.decode('utf-8') if stdout else None
        self.stderr_text = stderr.decode('utf-8') if stderr else None


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


def running_as_root() -> bool:
    return os.geteuid() == 0


def isolate_root_cmd(cmd: List[str], cwd=None) -> List[str]:
    if not running_as_root():
        return cmd
    base_root_isolator = [
        'systemd-run', '--pipe', '--wait',
        '-p', 'DynamicUser=yes',
        '-p', 'CacheDirectory=pikaur',
        '-E', 'HOME=/tmp',
    ]
    if cwd is not None:
        base_root_isolator += ['-p', 'WorkingDirectory=' + cwd]
    return base_root_isolator + cmd


def sudo(cmd: List[str]) -> List[str]:
    if running_as_root():
        return cmd
    return ['sudo', ] + cmd


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


def return_exception(fun: Callable) -> Callable:
    def decorator(*args, **kwargs):
        try:
            return fun(*args, **kwargs)
        except Exception as exc:
            return exc
    return decorator


def just_copy_damn_tree(from_path, to_path) -> None:
    if not os.path.exists(to_path):
        os.makedirs(to_path)

    if os.path.isdir(from_path):
        from_path = f'{from_path}/.'
    cmd_args = ['cp', '-r', from_path, to_path]

    result = spawn(cmd_args)
    if result.returncode != 0:
        remove_dir(to_path)
        result = interactive_spawn(cmd_args)
        if result.returncode != 0:
            raise Exception(_(f"Can't copy '{from_path}' to '{to_path}'."))


def get_editor() -> Optional[List[str]]:
    editor_line = os.environ.get('VISUAL') or os.environ.get('EDITOR')
    if editor_line:
        return editor_line.split(' ')
    for editor in ('vim', 'nano', 'mcedit', 'edit'):
        result = spawn(['which', editor])
        if result.returncode == 0:
            return [editor, ]
    print_stderr(
        '{} {}'.format(
            color_line('error:', 9),
            _("no editor found. Try setting $VISUAL or $EDITOR.")
        )
    )
    return None
