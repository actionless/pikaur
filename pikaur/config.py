"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import configparser
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from .i18n import translate

if TYPE_CHECKING:
    from typing_extensions import NotRequired, TypedDict

    class DeprecatedConfigValue(TypedDict):
        section: str
        option: str
        transform: NotRequired[Callable[[str, configparser.ConfigParser], str]]

    class ConfigValueType(TypedDict):
        data_type: str
        default: NotRequired[str]
        deprecated: NotRequired[DeprecatedConfigValue]
        migrated: NotRequired[bool]


DEFAULT_CONFIG_ENCODING = 'utf-8'


RUNNING_AS_ROOT = os.geteuid() == 0


VERSION = '1.14.4-dev'

_USER_CACHE_HOME = os.environ.get(
    "XDG_CACHE_HOME",
    os.path.join(Path.home(), ".cache/")
)
if RUNNING_AS_ROOT:
    CACHE_ROOT = '/var/cache/pikaur'
else:
    CACHE_ROOT = os.path.join(_USER_CACHE_HOME, 'pikaur/')

BUILD_CACHE_PATH = os.path.join(CACHE_ROOT, 'build')
PACKAGE_CACHE_PATH = os.path.join(CACHE_ROOT, 'pkg')

CONFIG_ROOT = os.environ.get(
    "XDG_CONFIG_HOME",
    os.path.join(Path.home(), ".config/")
)

DATA_ROOT = os.path.join(
    os.environ.get(
        "XDG_DATA_HOME",
        os.path.join(Path.home(), ".local/share/")
    ), "pikaur"
)
_OLD_AUR_REPOS_CACHE_PATH = os.path.join(CACHE_ROOT, 'aur_repos')
if RUNNING_AS_ROOT:
    AUR_REPOS_CACHE_PATH = os.path.join(CACHE_ROOT, 'aur_repos')
else:
    AUR_REPOS_CACHE_PATH = os.path.join(DATA_ROOT, 'aur_repos')

if RUNNING_AS_ROOT:
    BUILD_DEPS_LOCK = os.path.join(_USER_CACHE_HOME, 'pikaur_build_deps.lock')
else:
    BUILD_DEPS_LOCK = '/tmp/pikaur_build_deps.lock'  # nosec B108


def get_config_path() -> str:
    config_flag = '--pikaur-config'
    if config_flag in sys.argv:
        return sys.argv[
            sys.argv.index(config_flag) + 1
        ]
    return os.path.join(
        CONFIG_ROOT,
        "pikaur.conf"
    )


CONFIG_PATH = get_config_path()


CONFIG_SCHEMA: dict[str, dict[str, 'ConfigValueType']] = {
    'sync': {
        'AlwaysShowPkgOrigin': {
            'data_type': 'bool',
            'default': 'no',
        },
        'DevelPkgsExpiration': {
            'data_type': 'int',
            'default': '-1',
        },
        'UpgradeSorting': {
            'data_type': 'str',
            'default': 'versiondiff'
        },
        'ShowDownloadSize': {
            'data_type': 'bool',
            'default': 'no',
        },
        'IgnoreOutofdateAURUpgrades': {
            'data_type': 'bool',
            'default': 'no',
        },
    },
    'build': {
        'KeepBuildDir': {
            'data_type': 'bool',
            'default': 'no',
        },
        'KeepDevBuildDir': {
            'data_type': 'bool',
            'default': 'yes',
        },
        'KeepBuildDeps': {
            'data_type': 'bool',
            'default': 'no',
        },
        'GpgDir': {
            'data_type': 'str',
            'default': ('/etc/pacman.d/gnupg/' if RUNNING_AS_ROOT else '')
        },
        'SkipFailedBuild': {
            'data_type': 'bool',
            'default': 'no',
        },
        'AlwaysUseDynamicUsers': {
            'data_type': 'bool',
            'default': 'no',
        },
        'NoEdit': {
            'data_type': 'bool',
            'deprecated': {
                'section': 'review',
                'option': 'NoEdit',
            },
        },
        'DontEditByDefault': {
            'data_type': 'bool',
            'deprecated': {
                'section': 'review',
                'option': 'DontEditByDefault',
            },
        },
        'NoDiff': {
            'data_type': 'bool',
            'deprecated': {
                'section': 'review',
                'option': 'NoDiff',
            },
        },
        'GitDiffArgs': {
            'data_type': 'str',
            'deprecated': {
                'section': 'review',
                'option': 'GitDiffArgs',
            },
        },
        'IgnoreArch': {
            'data_type': 'bool',
            'default': 'no'
        },
    },
    'review': {
        'NoEdit': {
            'data_type': 'bool',
            'default': 'no',
        },
        'DontEditByDefault': {
            'data_type': 'bool',
            'default': 'no',
        },
        'NoDiff': {
            'data_type': 'bool',
            'default': 'no',
        },
        'GitDiffArgs': {
            'data_type': 'str',
            'default': '--ignore-space-change,--ignore-all-space',
        },
        'DiffPager': {
            'data_type': 'str',
            'default': 'auto'
        },
        'HideDiffFiles': {
            'data_type': 'str',
            'default': '.SRCINFO'
        },
    },
    'colors': {
        'Version': {
            'data_type': 'int',
            'default': '10',
        },
        'VersionDiffOld': {
            'data_type': 'int',
            'default': '11',
        },
        'VersionDiffNew': {
            'data_type': 'int',
            'default': '9',
        },
    },
    'ui': {
        'RequireEnterConfirm': {
            'data_type': 'bool',
            'default': 'yes'
        },
        'DiffPager': {
            'data_type': 'str',
            'deprecated': {
                'section': 'review',
                'option': 'DiffPager',
            },
        },
        'PrintCommands': {
            'data_type': 'bool',
            'default': 'no'
        },
        'AurSearchSorting': {
            'data_type': 'str',
            'default': 'hottest'
        },
        'DisplayLastUpdated': {
            'data_type': 'bool',
            'default': 'no'
        },
        'GroupByRepository': {
            'data_type': 'bool',
            'default': 'yes'
        },
        'ReverseSearchSorting': {
            'data_type': 'bool',
            'default': 'no'
        },
        'WarnAboutPackageUpdates': {
            'data_type': 'str',
            'default': ''
        },
    },
    'misc': {
        'SudoLoopInterval': {
            'data_type': 'int',
            'default': '59',
        },
        'PacmanPath': {
            'data_type': 'str',
            'default': 'pacman'
        },
        'PrivilegeEscalationTool': {
            'data_type': 'str',
            'default': 'sudo',
        },
        'AurHost': {
            'data_type': 'str',
            'deprecated': {
                'section': 'network',
                'option': 'AurUrl',
                'transform': lambda old_value, config: f'https://{old_value}'
            },
        },
        'NewsUrl': {
            'data_type': 'str',
            'deprecated': {
                'section': 'network',
                'option': 'NewsUrl',
            },
        },
    },
    'network': {
        'AurUrl': {
            'data_type': 'str',
            'default': 'https://aur.archlinux.org',
        },
        'NewsUrl': {
            'data_type': 'str',
            'default': 'https://www.archlinux.org/feeds/news/',
        },
        'Socks5Proxy': {
            'data_type': 'str',
            'default': '',
        },
        'AurHttpProxy': {
            'data_type': 'str',
            'default': '',
        },
        'AurHttpsProxy': {
            'data_type': 'str',
            'default': '',
        },
    },
}


def get_key_type(section_name: str, key_name: str) -> str | None:
    config_value: 'ConfigValueType' | None = CONFIG_SCHEMA.get(section_name, {}).get(key_name, None)
    if not config_value:
        return None
    return config_value.get('data_type')


def write_config(config: configparser.ConfigParser | None = None) -> None:
    if not config:
        config = configparser.ConfigParser()
    need_write = False
    for section_name, section in CONFIG_SCHEMA.items():
        if section_name not in config:
            config[section_name] = {}
        for option_name, option_schema in section.items():
            if option_schema.get('migrated'):
                need_write = True
                continue
            if option_schema.get('deprecated'):
                continue
            if option_name not in config[section_name]:
                config[section_name][option_name] = option_schema['default']
                need_write = True
    if need_write:
        if not os.path.exists(CONFIG_ROOT):
            os.makedirs(CONFIG_ROOT)
        with open(CONFIG_PATH, 'w', encoding=DEFAULT_CONFIG_ENCODING) as configfile:
            config.write(configfile)


def str_to_bool(value: str) -> bool:
    # pylint:disable=protected-access
    result: bool = \
        configparser.RawConfigParser()._convert_to_boolean(value)  # type: ignore[attr-defined]
    return result


class PikaurConfigItem:

    def __init__(self, section: configparser.SectionProxy, key: str) -> None:
        self.section = section
        self.key = key
        self.value = self.section.get(key)

    def get_bool(self) -> bool:
        if get_key_type(self.section.name, self.key) != 'bool':
            raise TypeError(f"{self.key} is not 'bool'")
        return str_to_bool(self.value)

    def get_int(self) -> int:
        if get_key_type(self.section.name, self.key) != 'int':
            raise TypeError(f"{self.key} is not 'int'")
        return int(self.value)

    def get_str(self) -> str:
        # note: it's basically needed for mypy
        if get_key_type(self.section.name, self.key) != 'str':
            raise TypeError(f"{self.key} is not 'str'")
        return str(self.value)

    def __str__(self) -> str:
        return self.get_str()

    def __eq__(self, item: Any) -> bool:
        result: bool = self.get_str() == item
        return result


class PikaurConfigSection():

    section: configparser.SectionProxy

    def __init__(self, section: configparser.SectionProxy) -> None:
        self.section = section

    def __getattr__(self, attr: str) -> PikaurConfigItem:
        return PikaurConfigItem(self.section, attr)

    def __repr__(self) -> str:
        return str(self.section)


class PikaurConfig():

    _config: configparser.ConfigParser

    @classmethod
    def get_config(cls) -> configparser.ConfigParser:
        if not getattr(cls, '_config', None):
            cls._config = configparser.ConfigParser()
            if not os.path.exists(CONFIG_PATH):
                write_config()
            cls._config.read(CONFIG_PATH, encoding=DEFAULT_CONFIG_ENCODING)
            cls.migrate_config()
            write_config(config=cls._config)
            cls.validate_config()
        return cls._config

    @classmethod
    def migrate_config(cls) -> None:
        for section_name, section in CONFIG_SCHEMA.items():
            for option_name, option_schema in section.items():
                if not option_schema.get('deprecated'):
                    continue

                new_section_name: str = option_schema['deprecated']['section']
                new_option_name: str = option_schema['deprecated']['option']
                transform: Callable[
                    [str, configparser.ConfigParser], str
                ] | None = option_schema['deprecated'].get('transform')

                old_value_was_migrated = False
                if (
                        new_section_name not in cls._config
                ) or (
                    cls._config[new_section_name].get(new_option_name) is None
                ):
                    value_to_migrate = cls._config[section_name].get(option_name)
                    if value_to_migrate is not None:
                        if transform:
                            value_to_migrate = transform(value_to_migrate, cls._config)
                        if new_section_name not in cls._config:
                            cls._config[new_section_name] = {}
                        cls._config[new_section_name][new_option_name] = value_to_migrate
                        CONFIG_SCHEMA[new_section_name][new_option_name]['migrated'] = True
                        old_value_was_migrated = True

                old_value_was_removed = False
                if option_name in cls._config[section_name]:
                    del cls._config[section_name][option_name]
                    CONFIG_SCHEMA[section_name][option_name]['migrated'] = True
                    old_value_was_removed = True

                if old_value_was_migrated or old_value_was_removed:
                    print(' '.join([
                        '::',
                        translate("warning:"),
                        translate('Migrating [{}]{} config option to [{}]{} = "{}"...').format(
                            section_name, option_name,
                            new_section_name, new_option_name,
                            cls._config[new_section_name][new_option_name]
                        ),
                        '\n',
                    ]))

    @classmethod
    def validate_config(cls) -> None:
        pacman_path = cls._config['misc']['PacmanPath']
        if pacman_path == 'pikaur' or pacman_path.endswith('/pikaur'):
            print("BAM! I am a shell bomb.")
            sys.exit(1)

    def __getattr__(self, attr: str) -> PikaurConfigSection:
        return PikaurConfigSection(self.get_config()[attr])
