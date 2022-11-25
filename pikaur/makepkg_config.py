"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import os
from typing import TypeVar

from .args import parse_args
from .config import CONFIG_ROOT
from .core import open_file, running_as_root


ConfigValueType = str | list[str] | None
ConfigFormat = dict[str, ConfigValueType]


FallbackValueT = TypeVar('FallbackValueT')


class ConfigReader():

    comment_prefixes = ('#', ';')

    _cached_config: dict[str, ConfigFormat] | None = None
    default_config_path: str
    list_fields: list[str] = []
    ignored_fields: list[str] = []

    @classmethod
    def _parse_line(cls, line: str) -> tuple[str | None, ConfigValueType]:
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
    def get_config(cls, config_path: str | None = None) -> ConfigFormat:
        config_path = config_path or cls.default_config_path
        if cls._cached_config is None:
            cls._cached_config = {}
        if not cls._cached_config.get(config_path):
            with open_file(config_path) as config_file:
                # pylint: disable=unsupported-assignment-operation
                cls._cached_config[config_path] = {
                    key: value
                    for key, value in [
                        cls._parse_line(line)
                        for line in config_file.readlines()
                    ] if key
                }
        # pylint: disable=unsubscriptable-object
        return cls._cached_config[config_path]

    @classmethod
    def get(
            cls,
            key: str,
            fallback: FallbackValueT | None = None,
            config_path: str | None = None
    ) -> ConfigValueType | FallbackValueT:
        return cls.get_config(config_path=config_path).get(key) or fallback


class MakepkgConfig():

    _user_makepkg_path: str | None = "unset"

    @classmethod
    def get_user_makepkg_path(cls) -> str | None:
        if cls._user_makepkg_path == 'unset':
            possible_paths = [
                os.path.expanduser('~/.makepkg.conf'),
                os.path.join(CONFIG_ROOT, "pacman/makepkg.conf"),
            ]
            config_path: str | None = None
            for path in possible_paths:
                if os.path.exists(path):
                    config_path = path
            cls._user_makepkg_path = config_path
        return cls._user_makepkg_path

    @classmethod
    def get(
            cls,
            key: str,
            fallback: FallbackValueT | None = None,
            config_path: str | None = None
    ) -> ConfigValueType | FallbackValueT:
        arg_path: str | None = parse_args().makepkg_config
        value: ConfigValueType | FallbackValueT = ConfigReader.get(
            key, fallback, config_path="/etc/makepkg.conf"
        )
        if cls.get_user_makepkg_path():
            value = ConfigReader.get(key, value, config_path=cls.get_user_makepkg_path())
        if arg_path:
            value = ConfigReader.get(key, value, config_path=arg_path)
        if config_path:
            value = ConfigReader.get(key, value, config_path=config_path)
        return value


CONFIG_PKGDEST = MakepkgConfig.get('PKGDEST')
if not isinstance(CONFIG_PKGDEST, str):
    CONFIG_PKGDEST = None
PKGDEST: str | None = os.environ.get('PKGDEST', CONFIG_PKGDEST)
if PKGDEST:
    PKGDEST = PKGDEST.replace('$HOME', '~')
    PKGDEST = os.path.expanduser(PKGDEST)


class MakePkgCommand:

    _cmd: list[str] | None = None
    pkgdest_skipped = False

    @classmethod
    def _apply_dynamic_users_workaround(cls) -> None:
        if running_as_root() and PKGDEST and (
                PKGDEST.startswith('/tmp') or  # nosec B108
                PKGDEST.startswith('/var/tmp')  # nosec B108
        ):
            if not cls._cmd:
                raise RuntimeError()
            cls._cmd = ['env', 'PKGDEST='] + cls._cmd
            cls.pkgdest_skipped = True

    @classmethod
    def get(cls) -> list[str]:
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
