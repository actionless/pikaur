import os
import shutil
import subprocess
import enum
import codecs
from distutils.dir_util import copy_tree
from typing import Dict, Any, List, Iterable, Tuple, Union, Callable


NOT_FOUND_ATOM = object()


class PackageSource(enum.Enum):
    REPO = enum.auto()
    AUR = enum.auto()
    LOCAL = enum.auto()


class InteractiveSpawn(subprocess.Popen):

    stdout_text: str = None
    stderr_text: str = None

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


class DataType():

    def __init__(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __setattr__(self, key: str, value: Any) -> None:
        if getattr(self, key, NOT_FOUND_ATOM) is NOT_FOUND_ATOM:
            raise TypeError(
                f"'{self.__class__.__name__}' does "
                f"not have attribute '{key}'"
            )
        super().__setattr__(key, value)


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
    return codecs.open(
        file_path, mode, encoding=encoding, errors='ignore', **kwargs
    )


CONFIG_VALUE_TYPE = Union[str, List[str]]
CONFIG_FORMAT = Dict[str, CONFIG_VALUE_TYPE]


class ConfigReader():

    comment_prefixes = ('#', ';')

    _cached_config: Dict[str, CONFIG_FORMAT] = None
    default_config_path: str = None  # noqa
    list_fields: List[str] = []
    ignored_fields: List[str] = []

    @classmethod
    def _parse_line(cls, line: str) -> Tuple[str, CONFIG_VALUE_TYPE]:
        blank = (None, None, )
        if line.startswith(' '):
            return blank
        if '=' not in line:
            return blank
        line = line.strip()
        for comment_prefix in cls.comment_prefixes:
            line, *_comments = line.split(comment_prefix)

        key, *values = line.split('=')
        value = '='.join(values)
        key = key.strip()
        value = value.strip()

        if key in cls.ignored_fields:
            return blank

        if value:
            value = value.strip('"').strip("'")
        else:
            return key, value

        if key in cls.list_fields:
            list_value = value.split()
            return key, list_value

        return key, value

    @classmethod
    def get_config(cls, config_path: str = None) -> CONFIG_FORMAT:
        config_path = config_path or cls.default_config_path
        if not cls._cached_config:
            cls._cached_config = {}
        if not cls._cached_config.get(config_path):
            with open_file(config_path) as config_file:
                cls._cached_config[config_path] = {
                    key: value
                    for key, value in [
                        cls._parse_line(line)
                        for line in config_file.readlines()
                    ] if key
                }
        return cls._cached_config[config_path]

    @classmethod
    def get(cls, key: str, fallback: Any = None, config_path: str = None) -> Any:
        return cls.get_config(config_path=config_path).get(key) or fallback


def remove_dir(dir_path: str) -> None:
    try:
        shutil.rmtree(dir_path)
    except PermissionError:
        interactive_spawn(['sudo', 'rm', '-rf', dir_path])


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
    if not os.path.exists(to_path):
        shutil.copytree(from_path, to_path, symlinks=True)
    else:
        copy_tree(from_path, to_path, preserve_symlinks=True)
