""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import os
from typing import (
    Dict, Any, List, Tuple, Union, Optional,
)

from .core import open_file
from .config import CONFIG_ROOT


CONFIG_VALUE_TYPE = Union[None, str, List[str]]
CONFIG_FORMAT = Dict[str, CONFIG_VALUE_TYPE]


class ConfigReader():

    comment_prefixes = ('#', ';')

    _cached_config: Optional[Dict[str, CONFIG_FORMAT]] = None
    default_config_path: str
    list_fields: List[str] = []
    ignored_fields: List[str] = []

    @classmethod
    def _parse_line(cls, line: str) -> Tuple[Optional[str], CONFIG_VALUE_TYPE]:
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


class MakepkgConfig():

    _user_makepkg_path: Optional[str] = "unset"

    @classmethod
    def get_user_makepkg_path(cls) -> Optional[str]:
        if cls._user_makepkg_path == 'unset':
            possible_paths = [
                os.path.expanduser('~/.makepkg.conf'),
                os.path.join(CONFIG_ROOT, "pacman/makepkg.conf"),
            ]
            config_path: Optional[str] = None
            for path in possible_paths:
                if os.path.exists(path):
                    config_path = path
            cls._user_makepkg_path = config_path
        return cls._user_makepkg_path

    @classmethod
    def get(cls, key: str, fallback: Any = None, config_path: str = None) -> Any:
        value = ConfigReader.get(key, fallback, config_path="/etc/makepkg.conf")
        if cls.get_user_makepkg_path():
            value = ConfigReader.get(key, value, config_path=cls.get_user_makepkg_path())
        if config_path:
            value = ConfigReader.get(key, value, config_path=config_path)
        return value
