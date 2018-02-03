import os

CACHE_ROOT = os.path.expanduser('~/.cache/pikaur/')
AUR_REPOS_CACHE = os.path.join(CACHE_ROOT, 'aur_repos')
PKG_CACHE = os.path.join(CACHE_ROOT, 'pkg')  # @TODO: copy packages to cache
BUILD_CACHE = os.path.join(CACHE_ROOT, 'build')
LOCK_FILE_PATH = os.path.join(CACHE_ROOT, 'db.lck')  # @TODO: lock transaction?

VERSION = '0.2'
