""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import os
import sys
import configparser
from typing import Union

from .core import running_as_root, open_file


VERSION = '1.0-dev'

_USER_CACHE_HOME = os.environ.get(
    "XDG_CACHE_HOME",
    os.path.join(os.environ["HOME"], ".cache/")
)
if running_as_root():
    CACHE_ROOT = '/var/cache/pikaur'
else:
    CACHE_ROOT = os.path.join(_USER_CACHE_HOME, 'pikaur/')

AUR_REPOS_CACHE_PATH = os.path.join(CACHE_ROOT, 'aur_repos')
BUILD_CACHE_PATH = os.path.join(CACHE_ROOT, 'build')
PACKAGE_CACHE_PATH = os.path.join(CACHE_ROOT, 'pkg')

CONFIG_ROOT = os.environ.get(
    "XDG_CONFIG_HOME",
    os.path.join(os.environ["HOME"], ".config/")
)
CONFIG_PATH = os.path.join(
    CONFIG_ROOT,
    "pikaur.conf"
)


_CONFIG_SCHEMA = {
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
        'NoEdit': {
            'type': 'bool',
            'default': 'no',
        },
        'NoDiff': {
            'type': 'bool',
            'default': 'no',
        }
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
    },
    'misc': {
        'PacmanPath': {
            'type': 'str',
            'default': 'pacman'
        },
    },
}


ConfigValueTypes = Union[str, bool, int]


def write_config(config: configparser.ConfigParser = None) -> None:
    if not config:
        config = configparser.ConfigParser()
    need_write = False
    for section_name, section in _CONFIG_SCHEMA.items():
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
        if _CONFIG_SCHEMA[section.name].get(key, {}).get('type') != 'str':
            raise TypeError(f"{key} is not 'str'")
        return section.get(key, *args)

    def get_int(self, key: str) -> int:
        section = self.section
        if _CONFIG_SCHEMA[section.name].get(key, {}).get('type') != 'int':
            raise TypeError(f"{key} is not 'int'")
        return section.getint(key)

    def get_bool(self, key: str) -> bool:
        section = self.section
        if _CONFIG_SCHEMA[section.name].get(key, {}).get('type') != 'bool':
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

    @classmethod
    def get(cls, section: str, key: str, *args) -> ConfigValueTypes:
        return getattr(cls(), section).get(key, *args)
