""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import os
import sys
import configparser
import shutil
from pathlib import Path
from typing import Dict, Optional

from .core import running_as_root, open_file


VERSION = '1.4.1-dev'

_USER_CACHE_HOME = os.environ.get(
    "XDG_CACHE_HOME",
    os.path.join(Path.home(), ".cache/")
)
if running_as_root():
    CACHE_ROOT = '/var/cache/pikaur'
else:
    CACHE_ROOT = os.path.join(_USER_CACHE_HOME, 'pikaur/')

BUILD_CACHE_PATH = os.path.join(CACHE_ROOT, 'build')
PACKAGE_CACHE_PATH = os.path.join(CACHE_ROOT, 'pkg')

CONFIG_ROOT = os.environ.get(
    "XDG_CONFIG_HOME",
    os.path.join(Path.home(), ".config/")
)

DATA_ROOT = os.environ.get(
    "XDG_DATA_HOME",
    os.path.join(Path.home(), ".local/share/pikaur")
)
_OLD_AUR_REPOS_CACHE_PATH = os.path.join(CACHE_ROOT, 'aur_repos')
if running_as_root():
    AUR_REPOS_CACHE_PATH = os.path.join(CACHE_ROOT, 'aur_repos')
else:
    AUR_REPOS_CACHE_PATH = os.path.join(DATA_ROOT, 'aur_repos')


def migrate_old_aur_repos_dir() -> None:
    if not (
            os.path.exists(_OLD_AUR_REPOS_CACHE_PATH) and not os.path.exists(AUR_REPOS_CACHE_PATH)
    ):
        return
    if not os.path.exists(DATA_ROOT):
        os.makedirs(DATA_ROOT)
    shutil.move(_OLD_AUR_REPOS_CACHE_PATH, AUR_REPOS_CACHE_PATH)

    from .pprint import print_warning, print_stderr
    from .i18n import _
    print_stderr()
    print_warning(
        _("AUR repos dir has been moved from '{old}' to '{new}'.".format(
            old=_OLD_AUR_REPOS_CACHE_PATH,
            new=AUR_REPOS_CACHE_PATH
        ))
    )
    print_stderr()


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


CONFIG_SCHEMA: Dict[str, Dict[str, Dict[str, str]]] = {
    'sync': {
        'AlwaysShowPkgOrigin': {
            'type': 'bool',
            'default': 'no',
        },
        'DevelPkgsExpiration': {
            'type': 'int',
            'default': '-1',
        },
        'UpgradeSorting': {
            'type': 'str',
            'default': 'versiondiff'
        },
    },
    'build': {
        'KeepBuildDir': {
            'type': 'bool',
            'default': 'no',
        },
        'KeepDevBuildDir': {
            'type': 'bool',
            'default': 'yes',
        },
        'SkipFailedBuild': {
            'type': 'bool',
            'default': 'no',
        },
        'AlwaysUseDynamicUsers': {
            'type': 'bool',
            'default': 'no',
        },
        # @TODO: move above to new `review` section?
        'NoEdit': {
            'type': 'bool',
            'default': 'no',
        },
        'DontEditByDefault': {
            'type': 'bool',
            'default': 'no',
        },
        'NoDiff': {
            'type': 'bool',
            'default': 'no',
        },
        'GitDiffArgs': {
            'type': 'str',
            'default': '--ignore-space-change,--ignore-all-space',
        },
    },
    'colors': {
        'Version': {
            'type': 'int',
            'default': '10',
        },
        'VersionDiffOld': {
            'type': 'int',
            'default': '11',
        },
        'VersionDiffNew': {
            'type': 'int',
            'default': '9',
        },
    },
    'ui': {
        'RequireEnterConfirm': {
            'type': 'bool',
            'default': 'yes'
        },
        'DiffPager': {
            'type': 'str',
            'default': 'auto'
        },
        'PrintCommands': {
            'type': 'bool',
            'default': 'no'
        },
    },
    'misc': {
        'SudoLoopInterval': {
            'type': 'int',
            'default': '59',
        },
        'PacmanPath': {
            'type': 'str',
            'default': 'pacman'
        },
    },
    'network': {
        'Socks5Proxy': {
            'type': 'str',
            'default': '',
        },
    },
}


def get_key_type(section_name: str, key_name: str) -> Optional[str]:
    return CONFIG_SCHEMA.get(section_name, {}).get(key_name, {}).get('type')


def write_config(config: configparser.ConfigParser = None) -> None:
    if not config:
        config = configparser.ConfigParser()
    need_write = False
    for section_name, section in CONFIG_SCHEMA.items():
        if section_name not in config:
            config[section_name] = {}
        for option_name, option_schema in section.items():
            if option_name not in config[section_name]:
                config[section_name][option_name] = option_schema['default']
                need_write = True
    if need_write:
        if not os.path.exists(CONFIG_ROOT):
            os.makedirs(CONFIG_ROOT)
        with open_file(CONFIG_PATH, 'w') as configfile:
            config.write(configfile)


class PikaurConfigSection():

    section: configparser.SectionProxy

    def __init__(self, section: configparser.SectionProxy) -> None:
        self.section = section

    def __getattr__(self, attr) -> str:
        return self.get_str(attr)

    def get_str(self, key: str, *args) -> str:
        section = self.section
        if get_key_type(section.name, key) != 'str':
            raise TypeError(f"{key} is not 'str'")
        return section.get(key, *args)

    def get_int(self, key: str) -> int:
        section = self.section
        if get_key_type(section.name, key) != 'int':
            raise TypeError(f"{key} is not 'int'")
        return section.getint(key)

    def get_bool(self, key: str) -> bool:
        section = self.section
        if get_key_type(section.name, key) != 'bool':
            raise TypeError(f"{key} is not 'bool'")
        return section.getboolean(key)


class PikaurConfig():

    _config: configparser.ConfigParser

    @classmethod
    def get_config(cls) -> configparser.ConfigParser:
        if not getattr(cls, '_config', None):
            cls._config = configparser.ConfigParser()
            if not os.path.exists(CONFIG_PATH):
                write_config()
            cls._config.read(CONFIG_PATH, encoding='utf-8')
            write_config(config=cls._config)
            cls.validate_config()
        return cls._config

    @classmethod
    def validate_config(cls) -> None:
        pacman_path = cls._config['misc']['PacmanPath']
        if pacman_path == 'pikaur' or pacman_path.endswith('/pikaur'):
            print("BAM! I am a shell bomb.")
            sys.exit(1)

    def __getattr__(self, attr: str) -> PikaurConfigSection:
        return PikaurConfigSection(self.get_config()[attr])
