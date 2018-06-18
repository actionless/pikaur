import sys

from pikaur.main import main


WRITE_DB = False
if (len(sys.argv) > 1) and sys.argv[1] == '--write-db':
    WRITE_DB = True


def pikaur(cmd):
    sys.argv = ['pikaur'] + cmd.split(' ') + (
        ['--noconfirm'] if '-S' in cmd else []
    )
    main()


pikaur('-V')

pikaur('-Sh')
pikaur('-Qh')


if WRITE_DB:

    # repo package
    pikaur('-S flac')

    # aur package
    pikaur('-S inxi')
