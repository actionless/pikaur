"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import configparser
import datetime
import os
import random
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from tempfile import gettempdir
from typing import TYPE_CHECKING

from .i18n import PIKAUR_NAME, translate

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any, Final, NotRequired

    from typing_extensions import TypedDict

    class DeprecatedConfigValue(TypedDict):
        section: str
        option: str
        transform: NotRequired[Callable[[str, configparser.ConfigParser], str]]

    class ConfigValueType(TypedDict):
        data_type: str
        default: NotRequired[str]
        old_default: NotRequired[str]
        deprecated: NotRequired[DeprecatedConfigValue]
        migrated: NotRequired[bool]


VERSION: "Final" = "1.26-dev"

DEFAULT_CONFIG_ENCODING: "Final" = "utf-8"
DEFAULT_INPUT_ENCODING: "Final" = "utf-8"
DEFAULT_TIMEZONE: "Final" = datetime.datetime.now().astimezone().tzinfo

BOOL: "Final" = "bool"
INT: "Final" = "int"
STR: "Final" = "str"


# DECORATION: "Final" = "::"
DECORATION: "Final" = "△ "
# DECORATION: "Final" = "⚡️"
# @TODO: make it configurable later on


class IntOrBoolSingleton(int):

    value: int

    @classmethod
    def set_value(cls, value: int) -> None:
        cls.value = value

    @classmethod
    def init_value(cls) -> int:
        return 0

    @classmethod
    def get_value(cls) -> int:
        if getattr(cls, "value", None) is None:
            cls.value = cls.init_value()
        return cls.value

    def __new__(cls) -> int:  # type: ignore[misc]
        return cls.get_value()


class PathConfig(Path, ABC):

    value: Path

    @classmethod
    def set_value(cls, value: Path) -> None:
        cls.value = value

    @classmethod
    @abstractmethod
    def get_value(cls) -> Path:
        pass

    def __new__(cls) -> Path:  # type: ignore[misc]
        return cls.get_value()


class FixedPathSingleton(PathConfig):

    @classmethod
    @abstractmethod
    def init_value(cls) -> Path:
        pass

    @classmethod
    def get_value(cls) -> Path:
        if getattr(cls, "value", None) is None:
            cls.value = cls.init_value()
        return cls.value


def pre_arg_parser(key: str, fallback: str) -> str:
    if key in sys.argv:
        return sys.argv[
            sys.argv.index(key) + 1
        ]
    found = [
        arg.split("=", maxsplit=1)[1]
        for arg in sys.argv
        if (
            "=" in arg
            and arg.startswith(key)
        )
    ]
    if found:
        return found[0]
    return fallback


class CustomUserId(IntOrBoolSingleton):
    @classmethod
    def init_value(cls) -> int:
        return int(pre_arg_parser("--user-id", "0"))

    @classmethod
    def update_fallback(cls, new_id: int) -> None:
        cls.set_value(cls() or new_id)


class RunningAsRoot(IntOrBoolSingleton):
    @classmethod
    def init_value(cls) -> int:
        return os.geteuid() == 0


class UsingDynamicUsers(IntOrBoolSingleton):
    @classmethod
    def get_value(cls) -> int:
        return RunningAsRoot() and not CustomUserId()


class Home(FixedPathSingleton):
    @classmethod
    def init_value(cls) -> Path:
        home_dir_set = pre_arg_parser("--home-dir", "")
        return Path(home_dir_set) if home_dir_set else Path.home()


class _UserTempRoot(FixedPathSingleton):
    @classmethod
    def init_value(cls) -> Path:
        return Path(gettempdir())


class _CachePathDefault(FixedPathSingleton):
    @classmethod
    def init_value(cls) -> Path:
        return Path(
            pre_arg_parser("--xdg-cache-home", "")
            or os.environ.get(
                "XDG_CACHE_HOME",
            )
            or Home() / ".cache/",
        )


class _UserCacheRoot(FixedPathSingleton):
    @classmethod
    def init_value(cls) -> Path:
        return Path(
            pre_arg_parser("--xdg-cache-home", "")
            or os.environ.get(
                "XDG_CACHE_HOME",
            )
            or Path(PikaurConfig().misc.CachePath.get_str()),
        )


class CacheRoot(PathConfig):
    @classmethod
    def get_value(cls) -> Path:
        return (
            Path("/var/cache/pikaur")
            if UsingDynamicUsers() else
            _UserCacheRoot() / "pikaur/"
        )


class BuildCachePath(PathConfig):
    @classmethod
    def get_value(cls) -> Path:
        return CacheRoot() / "build"


class PackageCachePath(PathConfig):
    @classmethod
    def get_value(cls) -> Path:
        return CacheRoot() / "pkg"


class ConfigRoot(FixedPathSingleton):
    @classmethod
    def init_value(cls) -> Path:
        return Path(
            pre_arg_parser("--xdg-config-home", "")
            or os.environ.get(
                "XDG_CONFIG_HOME",
            )
            or Home() / ".config/",
        )


class _DataPathDefault(FixedPathSingleton):
    @classmethod
    def init_value(cls) -> Path:
        return Path(
            pre_arg_parser("--xdg-data-home", "")
            or os.environ.get(
                "XDG_DATA_HOME",
            )
            or Home() / ".local/share/",
        )


class DataRoot(FixedPathSingleton):
    @classmethod
    def init_value(cls) -> Path:
        return (
            Path(
                pre_arg_parser("--xdg-data-home", "")
                or os.environ.get(
                    "XDG_DATA_HOME",
                )
                or PikaurConfig().misc.DataPath.get_str(),
            ) / "pikaur"
        )


class _OldAurReposCachePath(PathConfig):
    # @TODO: remove this migration thing?
    @classmethod
    def get_value(cls) -> Path:
        return CacheRoot() / "aur_repos"


class AurReposCachePath(PathConfig):
    @classmethod
    def get_value(cls) -> Path:
        return (
            (CacheRoot() / "aur_repos")
            if UsingDynamicUsers() else
            (DataRoot() / "aur_repos")
        )


class BuildDepsLockPath(PathConfig):
    @classmethod
    def get_value(cls) -> Path:
        return (
            (
                _UserCacheRoot() if UsingDynamicUsers() else _UserTempRoot())
            / "pikaur_build_deps.lock"
        )


class PromptLockPath(PathConfig):
    @classmethod
    def get_value(cls) -> Path:
        return (
            (
                _UserCacheRoot() if UsingDynamicUsers() else _UserTempRoot()
            ) / f"pikaur_prompt_{random.randint(0, 999999)}.lock"  # nosec: B311   # noqa: S311
        )


class ConfigPath(PathConfig):
    @classmethod
    def get_value(cls) -> Path:
        config_overridden = pre_arg_parser("--pikaur-config", "")
        if config_overridden:
            return Path(config_overridden)
        return ConfigRoot() / "pikaur.conf"


class UpgradeSortingValues:
    VERSIONDIFF: "Final" = "versiondiff"
    PKGNAME: "Final" = "pkgname"
    REPO: "Final" = "repo"


class AurSearchSortingValues:
    HOTTEST: "Final" = "hottest"
    PKGNAME: "Final" = "pkgname"
    POPULARITY: "Final" = "popularity"
    NUMVOTES: "Final" = "numvotes"
    LASTMODIFIED: "Final" = "lastmodified"


class DiffPagerValues:
    AUTO: "Final" = "auto"
    ALWAYS: "Final" = "always"
    NEVER: "Final" = "never"


CONFIG_YES_VALUES: "Final" = ("yes", "y", "true", "1")


ConfigSchemaT = dict[str, dict[str, "ConfigValueType"]]


class ConfigSchema(ConfigSchemaT):

    config_schema: ConfigSchemaT | None = None

    def __new__(cls) -> "ConfigSchemaT":  # type: ignore[misc]
        if not cls.config_schema:
            cls.config_schema = {
                "sync": {
                    "AlwaysShowPkgOrigin": {
                        "data_type": BOOL,
                        "default": "no",
                    },
                    "DevelPkgsExpiration": {
                        "data_type": INT,
                        "default": "-1",
                    },
                    "UpgradeSorting": {
                        "data_type": STR,
                        "default": UpgradeSortingValues.VERSIONDIFF,
                    },
                    "ShowDownloadSize": {
                        "data_type": BOOL,
                        "default": "no",
                    },
                    "IgnoreOutofdateAURUpgrades": {
                        "data_type": BOOL,
                        "default": "no",
                    },
                },
                "build": {
                    "KeepBuildDir": {
                        "data_type": BOOL,
                        "default": "no",
                    },
                    "KeepDevBuildDir": {
                        "data_type": BOOL,
                        "default": "yes",
                    },
                    "KeepBuildDeps": {
                        "data_type": BOOL,
                        "default": "no",
                    },
                    "GpgDir": {
                        "data_type": STR,
                        "default": ("/etc/pacman.d/gnupg/" if RunningAsRoot() else ""),
                    },
                    "SkipFailedBuild": {
                        "data_type": BOOL,
                        "default": "no",
                    },
                    "DynamicUsers": {
                        "data_type": STR,
                        "default": "root",
                    },
                    "AlwaysUseDynamicUsers": {
                        "data_type": BOOL,
                        "default": "no",
                        "deprecated": {
                            "section": "build",
                            "option": "DynamicUsers",
                            "transform": (
                                lambda old_value, _config:
                                "always" if old_value == "yes" else "root"
                            ),
                        },
                    },
                    "NoEdit": {
                        "data_type": BOOL,
                        "deprecated": {
                            "section": "review",
                            "option": "NoEdit",
                        },
                    },
                    "DontEditByDefault": {
                        "data_type": BOOL,
                        "deprecated": {
                            "section": "review",
                            "option": "DontEditByDefault",
                        },
                    },
                    "NoDiff": {
                        "data_type": BOOL,
                        "deprecated": {
                            "section": "review",
                            "option": "NoDiff",
                        },
                    },
                    "GitDiffArgs": {
                        "data_type": STR,
                        "deprecated": {
                            "section": "review",
                            "option": "GitDiffArgs",
                        },
                    },
                    "IgnoreArch": {
                        "data_type": BOOL,
                        "default": "no",
                    },
                },
                "review": {
                    "NoEdit": {
                        "data_type": BOOL,
                        "default": "no",
                    },
                    "DontEditByDefault": {
                        "data_type": BOOL,
                        "default": "no",
                    },
                    "NoDiff": {
                        "data_type": BOOL,
                        "default": "no",
                    },
                    "GitDiffArgs": {
                        "data_type": STR,
                        "default": "--ignore-space-change,--ignore-all-space",
                    },
                    "DiffPager": {
                        "data_type": STR,
                        "default": DiffPagerValues.AUTO,
                    },
                    "HideDiffFiles": {
                        "data_type": STR,
                        "default": ".SRCINFO",
                    },
                },
                "colors": {
                    "Version": {
                        "data_type": INT,
                        "default": "10",
                    },
                    "VersionDiffOld": {
                        "data_type": INT,
                        "default": "11",
                    },
                    "VersionDiffNew": {
                        "data_type": INT,
                        "default": "9",
                    },
                },
                "ui": {
                    "RequireEnterConfirm": {
                        "data_type": BOOL,
                        "default": "yes",
                    },
                    "DiffPager": {
                        "data_type": STR,
                        "deprecated": {
                            "section": "review",
                            "option": "DiffPager",
                        },
                    },
                    "PrintCommands": {
                        "data_type": BOOL,
                        "default": "no",
                    },
                    "AurSearchSorting": {
                        "data_type": STR,
                        "default": AurSearchSortingValues.HOTTEST,
                    },
                    "DisplayLastUpdated": {
                        "data_type": BOOL,
                        "default": "no",
                    },
                    "GroupByRepository": {
                        "data_type": BOOL,
                        "default": "yes",
                    },
                    "ReverseSearchSorting": {
                        "data_type": BOOL,
                        "default": "no",
                    },
                    "WarnAboutPackageUpdates": {
                        "data_type": STR,
                        "default": "",
                    },
                    "WarnAboutNonDefaultPrivilegeEscalationTool": {
                        "data_type": BOOL,
                        "default": "yes",
                    },
                },
                "misc": {
                    "AurHost": {
                        "data_type": STR,
                        "deprecated": {
                            "section": "network",
                            "option": "AurUrl",
                            "transform": lambda old_value, _config: f"https://{old_value}",
                        },
                    },
                    "NewsUrl": {
                        "data_type": STR,
                        "deprecated": {
                            "section": "network",
                            "option": "NewsUrl",
                        },
                    },
                    "CachePath": {
                        "data_type": STR,
                        "default": str(_CachePathDefault()),
                    },
                    "DataPath": {
                        "data_type": STR,
                        "default": str(_DataPathDefault()),
                    },
                    "PacmanPath": {
                        "data_type": STR,
                        "default": "pacman",
                    },
                    "PrivilegeEscalationTool": {
                        "data_type": STR,
                        "default": "sudo",
                    },
                    "PrivilegeEscalationTarget": {
                        "data_type": STR,
                        "default": "pikaur",
                    },
                    "UserId": {
                        "data_type": INT,
                        "default": "0",
                    },
                    "PreserveEnv": {
                        "data_type": STR,
                        "default": (
                            "PKGDEST,VISUAL,EDITOR,http_proxy,https_proxy,ftp_proxy"
                            ",HTTP_PROXY,HTTPS_PROXY,FTP_PROXY,ALL_PROXY"
                        ),
                    },
                },
                "network": {
                    "AurUrl": {
                        "data_type": STR,
                        "default": "https://aur.archlinux.org",
                    },
                    "NewsUrl": {
                        "data_type": STR,
                        "default": "https://archlinux.org/feeds/news/",
                        "old_default": "https://www.archlinux.org/feeds/news/",
                    },
                    "Socks5Proxy": {
                        "data_type": STR,
                        "default": "",
                    },
                    "AurHttpProxy": {
                        "data_type": STR,
                        "default": "",
                    },
                    "AurHttpsProxy": {
                        "data_type": STR,
                        "default": "",
                    },
                },
            }
        return cls.config_schema


def get_key_type(section_name: str, key_name: str) -> str | None:
    config_value: ConfigValueType | None = ConfigSchema().get(section_name, {}).get(key_name, None)
    if not config_value:
        return None
    return config_value.get("data_type")


def write_config(config: configparser.ConfigParser | None = None) -> None:
    if not config:
        config = configparser.ConfigParser()
    need_write = False
    for section_name, section in ConfigSchema().items():
        if section_name not in config:
            config[section_name] = {}
        for option_name, option_schema in section.items():
            if option_schema.get("migrated"):
                need_write = True
                continue
            if option_schema.get("deprecated"):
                continue
            if option_name not in config[section_name]:
                config[section_name][option_name] = option_schema["default"]
                need_write = True
    if need_write:
        CustomUserId.update_fallback(int(config["misc"]["UserId"]))
        config_root = ConfigRoot()
        config_path = ConfigPath()
        if not config_root.exists():
            config_root.mkdir(parents=True)
        with config_path.open("w", encoding=DEFAULT_CONFIG_ENCODING) as configfile:
            config.write(configfile)
        if custom_user_id := CustomUserId():
            for path in (
                config_root,
                config_path,
            ):
                os.chown(path, custom_user_id, custom_user_id)


def str_to_bool(value: str) -> bool:
    return value.lower() in CONFIG_YES_VALUES


class PikaurConfigItem:

    def __init__(self, section: configparser.SectionProxy, key: str) -> None:
        self.section = section
        self.key = key
        self.value = self.section.get(key)
        self._type_error_template = translate(
            "{key} is not '{typeof}'",
        )

    def get_bool(self) -> bool:
        if get_key_type(self.section.name, self.key) != BOOL:
            not_bool_error = self._type_error_template.format(key=self.key, typeof=BOOL)
            raise TypeError(not_bool_error)
        return str_to_bool(self.value)

    def get_int(self) -> int:
        if get_key_type(self.section.name, self.key) != INT:
            not_int_error = self._type_error_template.format(key=self.key, typeof=INT)
            raise TypeError(not_int_error)
        return int(self.value)

    def get_str(self) -> str:
        # note: it"s basically needed for mypy
        if get_key_type(self.section.name, self.key) != STR:
            not_str_error = self._type_error_template.format(key=self.key, typeof=STR)
            raise TypeError(not_str_error)
        return str(self.value)

    def __str__(self) -> str:
        return self.get_str()

    def __hash__(self) -> int:
        return hash(self.get_str())

    def __eq__(self, item: "Any") -> bool:
        return hash(self) == hash(item)


class PikaurConfigSection:

    section: configparser.SectionProxy

    def __init__(self, section: configparser.SectionProxy) -> None:
        self.section = section

    def __getattr__(self, attr: str) -> PikaurConfigItem:
        return PikaurConfigItem(self.section, attr)

    def __repr__(self) -> str:
        return str(self.section)


class PikaurConfig:

    _config: configparser.ConfigParser

    @classmethod
    def get_config(cls) -> configparser.ConfigParser:
        if not getattr(cls, "_config", None):
            config_path = ConfigPath()
            cls._config = configparser.ConfigParser()
            if not config_path.exists():
                write_config()
            cls._config.read(config_path, encoding=DEFAULT_CONFIG_ENCODING)
            cls.migrate_config()
            write_config(config=cls._config)
            cls.validate_config()
            CustomUserId.update_fallback(int(cls._config["misc"]["UserId"]))
        return cls._config

    @classmethod
    def _migrate_deprecated_config_key(
            cls,
            option_schema: "ConfigValueType",
            section_name: str,
            option_name: str,
    ) -> None:
        new_section_name: str = option_schema["deprecated"]["section"]
        new_option_name: str = option_schema["deprecated"]["option"]
        transform: Callable[
            [str, configparser.ConfigParser], str,
        ] | None = option_schema["deprecated"].get("transform")

        old_value_was_migrated = False
        value_to_migrate = None
        if (section_name in cls._config) and ((
                new_section_name not in cls._config
        ) or (
            cls._config[new_section_name].get(new_option_name) is None
        )):
            value_to_migrate = cls._config[section_name].get(option_name)
            if value_to_migrate is not None:
                if transform:
                    new_value = transform(value_to_migrate, cls._config)
                else:
                    new_value = value_to_migrate
                if new_section_name not in cls._config:
                    cls._config[new_section_name] = {}
                cls._config[new_section_name][new_option_name] = new_value
                ConfigSchema()[new_section_name][new_option_name]["migrated"] = True
                old_value_was_migrated = True

        old_value_was_removed = False
        if (
                section_name in cls._config
        ) and (
            option_name in cls._config[section_name]
        ):
            del cls._config[section_name][option_name]
            ConfigSchema()[section_name][option_name]["migrated"] = True
            old_value_was_removed = True

        if old_value_was_migrated or old_value_was_removed:
            print(" ".join([  # noqa: T201
                DECORATION,
                translate("warning:"),
                translate(
                    'Migrating [{}]{}="{}" config option to [{}]{}="{}"...',
                ).format(
                    section_name, option_name,
                    value_to_migrate or "",
                    new_section_name, new_option_name,
                    cls._config[new_section_name][new_option_name],
                ),
                "\n",
            ]))

    @classmethod
    def _migrate_deprecated_config_value(
            cls,
            option_schema: "ConfigValueType",
            section_name: str,
            option_name: str,
    ) -> None:
        old_default = option_schema["old_default"]
        current_value = cls._config[section_name][option_name]
        if current_value == old_default:
            new_default_value = option_schema["default"]
            cls._config[section_name][option_name] = new_default_value
            ConfigSchema()[section_name][option_name]["migrated"] = True
            print(" ".join([  # noqa: T201
                DECORATION,
                translate("warning:"),
                translate(
                    'Migrating [{}]{}="{}" config option to ="{}"...',
                ).format(
                    section_name, option_name, current_value,
                    new_default_value,
                ),
                "\n",
            ]))

    @classmethod
    def migrate_config(cls) -> None:
        for section_name, section in ConfigSchema().items():
            for option_name, option_schema in section.items():
                if option_schema.get("old_default"):
                    cls._migrate_deprecated_config_value(option_schema, section_name, option_name)
                elif option_schema.get("deprecated"):
                    cls._migrate_deprecated_config_key(option_schema, section_name, option_name)

    @classmethod
    def validate_config(cls) -> None:
        pacman_path = cls._config["misc"]["PacmanPath"]
        if pacman_path in {PIKAUR_NAME, sys.argv[0]} or pacman_path.endswith(f"/{PIKAUR_NAME}"):
            print("BAM! I am a shell bomb.")  # noqa: T201
            sys.exit(1)

    def __getattr__(self, attr: str) -> PikaurConfigSection:
        return PikaurConfigSection(self.get_config()[attr])
