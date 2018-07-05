""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import sys
import tempfile
from subprocess import Popen

from typing import Optional, List, NoReturn

from pikaur.main import main


class TestPopen(Popen):
    stderr_text: Optional[str] = None
    stdout_text: Optional[str] = None


def spawn(cmd: List[str], **kwargs) -> TestPopen:
    with tempfile.TemporaryFile() as out_file:
        with tempfile.TemporaryFile() as err_file:
            proc = TestPopen(cmd, stdout=out_file, stderr=err_file, **kwargs)
            proc.communicate()
            out_file.seek(0)
            err_file.seek(0)
            proc.stdout_text = out_file.read().decode('utf-8')
            proc.stderr_text = err_file.read().decode('utf-8')
            return proc


def color_line(line: str, color_number: int) -> str:
    result = ''
    if color_number >= 8:
        result += "\033[0;1m"
        color_number -= 8
    result += f"\033[03{color_number}m{line}"
    # reset font:
    result += "\033[0;0m"
    return result


class CmdResult:

    def __init__(
            self,
            returncode: Optional[int] = None,
            stdout: Optional[str] = None,
            stderr: Optional[str] = None
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def pikaur(
        cmd: str, capture_stdout=True, capture_stderr=False
) -> CmdResult:
    returncode: Optional[int] = None
    stdout_text: Optional[str] = None
    stderr_text: Optional[str] = None

    class FakeExit(Exception):
        pass

    def fake_exit(code: Optional[int] = 0) -> NoReturn:
        nonlocal returncode
        returncode = code
        raise FakeExit()

    sys.argv = ['pikaur'] + cmd.split(' ') + (
        ['--noconfirm'] if '-S ' in cmd else []
    )
    print(color_line('\n => ', 10) + ' '.join(sys.argv))

    _real_exit = sys.exit
    sys.exit = fake_exit  # type: ignore

    with tempfile.TemporaryFile('w+', encoding='UTF-8') as out_file:
        with tempfile.TemporaryFile('w+', encoding='UTF-8') as err_file:
            out_file.isatty = lambda: False  # type: ignore
            err_file.isatty = lambda: False  # type: ignore

            _real_stdout = sys.stdout
            _real_stderr = sys.stderr
            if capture_stdout:
                sys.stdout = out_file  # type: ignore
            if capture_stderr:
                sys.stderr = err_file  # type: ignore

            try:
                main()
            except FakeExit:
                pass

            sys.stdout = _real_stdout
            sys.stderr = _real_stderr

            out_file.flush()
            err_file.flush()
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
