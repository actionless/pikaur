import sys

from pikaur_test.helpers import pikaur, assert_installed


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
    sorted(pikaur('-Ssq oomox').stdout.splitlines()) == ['oomox', 'oomox-git']
)


# tests which are modifying local package DB:
if WRITE_DB:

    # repo package
    pikaur('-S flac')
    assert_installed('flac')

    # aur package
    pikaur('-S inxi')
    assert_installed('inxi')


print('\n\n[OK] All tests passed\n')
