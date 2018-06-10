import os
import shutil
import subprocess
import enum
import codecs
import distutils
from distutils.dir_util import copy_tree
from typing import Any, List, Iterable, Callable, Optional

from .i18n import _
from .pprint import print_stderr, color_line


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
    return interactive_spawn(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)


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


def just_copy_damn_tree(from_path, to_path):
    if os.path.exists(to_path):
        try:
            copy_tree(from_path, to_path, preserve_symlinks=True)
        except (FileNotFoundError, distutils.errors.DistutilsFileError):
            remove_dir(to_path)
        else:
            return
    shutil.copytree(from_path, to_path, symlinks=True)


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
