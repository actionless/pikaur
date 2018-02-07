import os

VERSION = '0.3'

CACHE_ROOT = os.path.expanduser('~/.cache/pikaur/')
AUR_REPOS_CACHE = os.path.join(CACHE_ROOT, 'aur_repos')
PKG_CACHE = os.path.join(CACHE_ROOT, 'pkg')  # @TODO: copy packages to cache
BUILD_CACHE = os.path.join(CACHE_ROOT, 'build')
LOCK_FILE_PATH = os.path.join(CACHE_ROOT, 'db.lck')  # @TODO: lock transaction?

CONFIG_PATH = os.path.join(
    os.environ.get(
        "XDG_CONFIG_HOME",
        os.path.join(os.environ.get("HOME"), ".config/")
    ),
    "pikaur.conf"
)  # @TODO: like /etc/pacman.conf
