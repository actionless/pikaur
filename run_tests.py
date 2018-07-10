""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import sys
# monkey-patch to force always uncolored output:
from pikaur import pprint
pprint._ARGS.color = 'never'

from pikaur_test.helpers import (
    pikaur, assert_installed, assert_not_installed,
) # noqa


WRITE_DB = False
if (len(sys.argv) > 1) and sys.argv[1] == '--write-db':
    WRITE_DB = True


# just run info commands for coverage:
assert(
    not pikaur('-V').returncode
)
assert(
    not pikaur('-Sh').returncode
)
assert(
    not pikaur('-Qh').returncode
)


# unknown argument passed to pacman
assert(
    pikaur('-Zyx').returncode == 1
)


# search aur packages
assert(
    sorted(
        pikaur('-Ssq oomox').stdout.splitlines()
    ) == ['oomox', 'oomox-git']
)


# tests which are modifying local package DB:
if WRITE_DB:

    # aur package with repo deps
    pikaur('-S inxi')
    assert_installed('inxi')

    # repo package w/o deps
    pikaur('-S nano')
    assert_installed('nano')

    # repo package with deps
    pikaur('-S flac')
    assert_installed('flac')

    # aur package with aur dep and custom makepkg flags
    pikaur('-S pacaur-git --mflags=--skippgpcheck')
    assert_installed('pacaur-git')
    assert_installed('cower')

    # aur package with manually chosen aur dep (not working by now)
    # pacman('-Rs pacaur-git cower')
    # pikaur('-S pacaur-git cower-git')
    # assert_installed('pacaur-git')
    # assert_installed('cower-git')

    # 1 split package
    pikaur('-S python-pyalsaaudio')
    assert_installed('python-pyalsaaudio')
    assert_not_installed('python2-pyalsaaudio')

    # package removal (pacman wrapping)
    pikaur('-Rs python-pyalsaaudio --noconfirm')
    assert_not_installed('python-pyalsaaudio')

    # 2 split packages
    pikaur('-S python2-pyalsaaudio python-pyalsaaudio')
    assert_installed('python2-pyalsaaudio')
    assert_installed('python-pyalsaaudio')

    # split aur package with deps from aur (too long to build?)
    pikaur('-S zfs-dkms')
    assert_installed('zfs-dkms')
    assert_installed('zfs-utils')
    assert_installed('spl-dkms')
    assert_installed('spl-utils')


print('\n\n[OK] All tests passed\n')
