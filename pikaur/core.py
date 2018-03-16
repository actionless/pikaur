import configparser
import os
import shutil
import subprocess
import enum
import codecs
from typing import Dict, Any, List, Iterable


NOT_FOUND_ATOM = object()


class PackageSource(enum.Enum):
    REPO = enum.auto()
    AUR = enum.auto()
    LOCAL = enum.auto()


def interactive_spawn(cmd: List[str], **kwargs) -> subprocess.Popen:
    process = subprocess.Popen(cmd, **kwargs)
    process.communicate()
    return process


def running_as_root() -> bool:
    return os.geteuid() == 0


def isolate_root_cmd(cmd: List[str], cwd=None) -> List[str]:
    if not running_as_root():
        return cmd
    base_root_isolator = ['systemd-run', '--pipe', '--wait',
                          '-p', 'DynamicUser=yes',
                          '-p', 'CacheDirectory=pikaur']
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


class ConfigReader():

    _cached_config: Dict[str, configparser.SectionProxy] = None
    default_config_path: str = None
    list_fields: List[str] = []
    ignored_fields: List[str] = []

    @classmethod
    def _approve_line_for_parsing(cls, line: str) -> bool:
        if line.startswith(' '):
            return False
        if '=' not in line:
            return False
        if not cls.ignored_fields:
            return True
        field_area = line.split('=')[0]
        for field in cls.ignored_fields:
            if field in field_area:
                return False
        return True

    @classmethod
    def get_config(cls, config_path: str = None) -> configparser.SectionProxy:
        config_path = config_path or cls.default_config_path
        if not cls._cached_config:
            cls._cached_config = {}
        if not cls._cached_config.get(config_path):
            config = configparser.ConfigParser(
                allow_no_value=True,
                strict=False,
                inline_comment_prefixes=('#', ';')
            )
            with open(config_path) as config_file:
                config_string = '\n'.join(['[all]'] + [
                    line for line in config_file.readlines()
                    if cls._approve_line_for_parsing(line)
                ])
            config.read_string(config_string)
            cls._cached_config[config_path] = config['all']
        return cls._cached_config[config_path]

    @classmethod
    def get(cls, key: str, fallback: Any = None, config_path: str = None) -> Any:
        value = cls.get_config(config_path=config_path).get(key)
        if value:
            value = value.strip('"').strip("'")
        else:
            return fallback
        if key in cls.list_fields:
            return value.split()
        return value


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


def open_file(file_path: str, mode='r', encoding='utf-8'):
    return codecs.open(file_path, mode, encoding=encoding)
