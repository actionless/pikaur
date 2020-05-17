""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import os
from typing import (
    Dict, Any, List, Tuple, Union, Optional,
)

from .core import open_file, running_as_root
from .config import CONFIG_ROOT
from .args import parse_args


ConfigValueType = Union[None, str, List[str]]
ConfigFormat = Dict[str, ConfigValueType]


class ConfigReader():

    comment_prefixes = ('#', ';')

    _cached_config: Optional[Dict[str, ConfigFormat]] = None
    default_config_path: str
    list_fields: List[str] = []
    ignored_fields: List[str] = []

    @classmethod
    def _parse_line(cls, line: str) -> Tuple[Optional[str], ConfigValueType]:
        blank = (None, None, )
        if line.startswith(' '):
            return blank
        if '=' not in line:
            return blank
        line = line.strip()
        for comment_prefix in cls.comment_prefixes:
            line, *_comments = line.split(comment_prefix)

        key, _sep, value = line.partition('=')
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
    def get_config(cls, config_path: str = None) -> ConfigFormat:
        config_path = config_path or cls.default_config_path
        if cls._cached_config is None:
            cls._cached_config = {}
        if not cls._cached_config.get(config_path):
            with open_file(config_path) as config_file:
                cls._cached_config[config_path] = {  # pylint: disable=unsupported-assignment-operation
                    key: value
                    for key, value in [
                        cls._parse_line(line)
                        for line in config_file.readlines()
                    ] if key
                }
        return cls._cached_config[config_path]  # pylint: disable=unsubscriptable-object

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
        arg_path = parse_args().makepkg_config
        value = ConfigReader.get(key, fallback, config_path="/etc/makepkg.conf")
        if cls.get_user_makepkg_path():
            value = ConfigReader.get(key, value, config_path=cls.get_user_makepkg_path())
        if arg_path:
            value = ConfigReader.get(key, value, config_path=arg_path)
        if config_path:
            value = ConfigReader.get(key, value, config_path=config_path)
        return value


PKGDEST: Optional[str] = os.environ.get(
    'PKGDEST',
    MakepkgConfig.get('PKGDEST')
)
if PKGDEST:
    PKGDEST = PKGDEST.replace('$HOME', '~')
    PKGDEST = os.path.expanduser(PKGDEST)


class MakePkgCommand:

    _cmd: Optional[List[str]] = None
    pkgdest_skipped = False

    @classmethod
    def _apply_dynamic_users_workaround(cls):
        if running_as_root() and PKGDEST and (
                PKGDEST.startswith('/tmp') or
                PKGDEST.startswith('/var/tmp')
        ):
            cls._cmd = ['env', 'PKGDEST='] + cls._cmd
            cls.pkgdest_skipped = True

    @classmethod
    def get(cls) -> List[str]:
        if cls._cmd is None:
            args = parse_args()
            makepkg_flags = (
                args.mflags.split(',') if args.mflags else []
            )
            config_args = (
                ['--config', args.makepkg_config] if args.makepkg_config else []
            )
            cls._cmd = [args.makepkg_path or 'makepkg', ] + makepkg_flags + config_args
            cls._apply_dynamic_users_workaround()
        return cls._cmd
