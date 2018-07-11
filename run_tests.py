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
    pikaur('-S pacaur --mflags=--skippgpcheck')
    assert_installed('pacaur')
    assert_installed('cower')

    # aur package with manually chosen aur dep (not working by now)
    # pacman('-Rs pacaur cower')
    # pikaur('-S pacaur cower-git')
    # assert_installed('pacaur')
    # assert_installed('cower-git')

    # # Arch Wiki: Reliable parser ############################################
    # pikaur('-S aws-cli-git')
    # assert_installed('aws-cli-git')
    # # python-tox dep is not available now

    # # Arch Wiki: Split packages #############################################

    # Split packages 1
    pikaur('-S clion')
    assert_installed('clion')

    # Split packages 2: libc++
    pikaur('-S libc++')
    assert_installed('libc++')

    # Split packages 2: libc++abi
    pikaur('-S libc++abi')
    assert_installed('libc++abi')

    # Split packages 3: 1 split package
    pikaur('-S python-pyalsaaudio')
    assert_installed('python-pyalsaaudio')
    assert_not_installed('python2-pyalsaaudio')

    # package removal (pacman wrapping test)
    pikaur('-Rs python-pyalsaaudio --noconfirm')
    assert_not_installed('python-pyalsaaudio')

    # Split packages 3: 2 split packages
    pikaur('-S python2-pyalsaaudio python-pyalsaaudio')
    assert_installed('python2-pyalsaaudio')
    assert_installed('python-pyalsaaudio')

    # # Based on GH-issues: ###################################################

    # split aur package with deps from aur (too long to build so use fake makepkg)
    pikaur('-S zfs-dkms', fake_makepkg=True)
    assert_installed('zfs-dkms')
    assert_installed('zfs-utils')
    assert_installed('spl-dkms')
    assert_installed('spl-utils')


print('\n\n[OK] All tests passed\n')
