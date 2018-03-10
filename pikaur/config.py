import os
import configparser

from .core import running_as_root

VERSION = '0.8-dev'

if running_as_root():
    CACHE_ROOT = '/var/cache/pikaur'
else:
    CACHE_ROOT = os.path.expanduser('~/.cache/pikaur/')

AUR_REPOS_CACHE_DIR = 'aur_repos'
BUILD_CACHE_DIR = 'build'

CONFIG_PATH = os.path.join(
    os.environ.get(
        "XDG_CONFIG_HOME",
        os.path.join(os.environ.get("HOME"), ".config/")
    ),
    "pikaur.conf"
)


_CONFIG_SCHEMA = {
    'sync': {
        'AlwaysShowPkgOrigin': {
            'type': 'bool',
            'default': 'no',
        },
    }
}


def write_config(config=None):
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
        with open(CONFIG_PATH, 'w') as configfile:
            config.write(configfile)


class PikaurConfigSection():

    section: configparser.SectionProxy = None

    def __init__(self, section):
        self.section = section

    def get(self, key, *args):
        section = self.section
        if _CONFIG_SCHEMA[section.name].get(key, {}).get('type') == 'bool':
            return section.getboolean(key, *args)
        else:
            return section.get(key, *args)


class PikaurConfig():

    _config: configparser.ConfigParser = None

    bool_fields = (
        'AlwaysShowPkgOrigin',
    )

    @classmethod
    def get_config(cls):
        if not cls._config:
            cls._config = configparser.ConfigParser()
            if not os.path.exists(CONFIG_PATH):
                write_config()
            cls._config.read = cls._config.read(CONFIG_PATH)
            write_config(config=cls._config)
        return cls._config

    def __getattr__(self, attr):
        return PikaurConfigSection(self.get_config()[attr])

    @classmethod
    def get(cls, section, key, *args):
        return getattr(cls(), section).get(key, *args)
