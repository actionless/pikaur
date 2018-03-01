import os

from .core import running_as_root

VERSION = '0.7-dev'

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
)  # @TODO: like /etc/pacman.conf
