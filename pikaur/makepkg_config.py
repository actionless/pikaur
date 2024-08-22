"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import os
from pathlib import Path
from typing import TYPE_CHECKING

from .args import parse_args
from .config import ConfigRoot, UsingDynamicUsers, _UserTempRoot
from .os_utils import open_file

if TYPE_CHECKING:
    from typing import Final, TypeVar

    FallbackValueT = TypeVar("FallbackValueT")

ConfigValueType = str | list[str] | None
ConfigFormat = dict[str, ConfigValueType]

CONFIG_LIST_FIELDS: "Final[list[str]]" = []
CONFIG_IGNORED_FIELDS: "Final[list[str]]" = []


class ConfigReader:

    COMMENT_PREFIXES: "Final" = ("#", ";")
    KEY_VALUE_DELIMITER: "Final" = "="

    _cached_config: dict[str | Path, ConfigFormat] | None = None
    default_config_path: str

    @classmethod
    def _parse_line(cls, line: str) -> tuple[str | None, ConfigValueType]:
        blank = (None, None)
        if line.startswith(" "):
            return blank
        if cls.KEY_VALUE_DELIMITER not in line:
            return blank
        line = line.strip()
        for comment_prefix in cls.COMMENT_PREFIXES:
            line, *_comments = line.split(comment_prefix)

        key, _sep, value = line.partition(cls.KEY_VALUE_DELIMITER)
        key = key.strip()
        value = value.strip()

        if key in CONFIG_IGNORED_FIELDS:
            return blank

        if value:
            value = value.strip('"').strip("'")
        else:
            return key, value

        if key in CONFIG_LIST_FIELDS:
            list_value = value.split()
            return key, list_value

        return key, value

    @classmethod
    def get_config(cls, config_path: str | Path | None = None) -> ConfigFormat:
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
            fallback: "FallbackValueT | None" = None,
            config_path: str | Path | None = None,
    ) -> "ConfigValueType | FallbackValueT":
        return cls.get_config(config_path=config_path).get(key) or fallback


class MakepkgConfig:

    _UNSET: "Final" = object()
    _user_makepkg_path: Path | object | None = _UNSET

    @classmethod
    def get_user_makepkg_path(cls) -> Path | None:
        if cls._user_makepkg_path is cls._UNSET:
            possible_paths = [
                Path("~/.makepkg.conf").expanduser(),
                ConfigRoot() / "pacman/makepkg.conf",
            ]
            config_path: Path | None = None
            for path in possible_paths:
                if path.exists():
                    config_path = path
            cls._user_makepkg_path = config_path
        return cls._user_makepkg_path if isinstance(cls._user_makepkg_path, Path) else None

    @classmethod
    def get(
            cls,
            key: str,
            fallback: "FallbackValueT | None" = None,
            config_path: str | None = None,
    ) -> "ConfigValueType | FallbackValueT":
        arg_path: str | None = parse_args().makepkg_config
        value: ConfigValueType | FallbackValueT = ConfigReader.get(
            key, fallback, config_path="/etc/makepkg.conf",
        )
        if cls.get_user_makepkg_path():
            value = ConfigReader.get(key, value, config_path=cls.get_user_makepkg_path())
        if arg_path:
            value = ConfigReader.get(key, value, config_path=arg_path)
        if config_path:
            value = ConfigReader.get(key, value, config_path=config_path)
        return value


def get_pkgdest() -> Path | None:
    config_pkgdest = MakepkgConfig.get("PKGDEST")
    if not isinstance(config_pkgdest, str):
        config_pkgdest = None
    pkgdest: str | None = os.environ.get("PKGDEST", config_pkgdest)
    if not pkgdest:
        return None
    return Path(pkgdest.replace("$HOME", "~")).expanduser()


class MakePkgCommand:

    _cmd: list[str] | None = None
    pkgdest_skipped = False

    @classmethod
    def _apply_dynamic_users_workaround(cls) -> None:
        if not UsingDynamicUsers():
            return
        pkgdest = str(get_pkgdest())
        if pkgdest and (
                pkgdest.startswith(
                    (str(_UserTempRoot()), "/tmp", "/var/tmp"),  # nosec B108  # noqa: S108
                )
        ):
            if not cls._cmd:
                raise RuntimeError
            cls._cmd = ["env", "PKGDEST=", *cls._cmd]
            cls.pkgdest_skipped = True

    @classmethod
    def get(cls) -> list[str]:
        if cls._cmd is None:
            args = parse_args()
            makepkg_flags = (
                args.mflags.split(",") if args.mflags else []
            )
            config_args = (
                ["--config", args.makepkg_config] if args.makepkg_config else []
            )
            cls._cmd = [args.makepkg_path or "makepkg", *makepkg_flags, *config_args]
            cls._apply_dynamic_users_workaround()
        return cls._cmd
