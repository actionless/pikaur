import sys
import tempfile
from typing import Optional

from pikaur.main import main
from pikaur.core import spawn, DataType
from pikaur import pprint


class CmdResult(DataType):

    returncode: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None


def pikaur(
        cmd: str, capture_stdout=True, capture_stderr=False
) -> CmdResult:
    returncode = None
    stdout_text = None
    stderr_text = None

    class FakeExit(Exception):
        pass

    def fake_exit(code):
        nonlocal returncode
        returncode = code
        raise FakeExit()

    sys.argv = ['pikaur'] + cmd.split(' ') + (
        ['--noconfirm'] if '-S ' in cmd else []
    )
    pprint._ARGS.color = 'always'
    print(pprint.color_line(' => ', 10) + ' '.join(sys.argv))
    pprint._ARGS.color = 'never'

    _real_exit = sys.exit
    sys.exit = fake_exit

    with tempfile.TemporaryFile('w+', encoding='UTF-8') as out_file:
        with tempfile.TemporaryFile('w+', encoding='UTF-8') as err_file:
            out_file.isatty = lambda: False
            err_file.isatty = lambda: False

            _real_stdout = sys.stdout
            _real_stderr = sys.stderr
            if capture_stdout:
                sys.stdout = out_file
            if capture_stderr:
                sys.stderr = err_file

            try:
                main()
            except FakeExit:
                pass

            sys.stdout = _real_stdout
            sys.stderr = _real_stderr

            out_file.seek(0)
            err_file.seek(0)
            stdout_text = out_file.read()
            stderr_text = err_file.read()

    sys.exit = _real_exit

    return CmdResult(
        returncode=returncode,
        stdout=stdout_text,
        stderr=stderr_text,
    )


def pacman(cmd: str) -> CmdResult:
    args = ['pacman'] + cmd.split(' ')
    proc = spawn(args)
    return CmdResult(
        returncode=proc.returncode,
        stdout=proc.stdout_text,
        stderr=proc.stderr_text,
    )


def assert_installed(pkg_name: str) -> None:
    assert(
        pacman(f'-Qi {pkg_name}').returncode == 0
    )
