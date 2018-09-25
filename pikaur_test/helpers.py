""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import sys
import os
import tempfile
from time import time
from subprocess import Popen
from unittest import TestCase
from typing import Optional, List, NoReturn, Union

# pylint:disable=no-name-in-module

from pikaur.main import main
from pikaur.args import CachedArgs, parse_args
from pikaur.pacman import PackageDB
from pikaur.pprint import get_term_width


TEST_DIR = os.path.dirname(os.path.realpath(__file__))


WRITE_DB = bool(os.environ.get('WRITE_DB'))


if WRITE_DB:
    # pylint:disable=protected-access
    from pikaur.config import CONFIG_PATH, PikaurConfig
    if os.path.exists(CONFIG_PATH):
        os.unlink(CONFIG_PATH)
    PikaurConfig._config = None  # type: ignore


class TestPopen(Popen):
    stderr_text: Optional[str] = None
    stdout_text: Optional[str] = None


def spawn(cmd: Union[str, List[str]], **kwargs) -> TestPopen:
    if isinstance(cmd, str):
        cmd = cmd.split(' ')
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


def log_stderr(line: str) -> None:
    sys.stderr.buffer.write((line + '\n').encode('utf-8'))
    sys.stderr.buffer.flush()


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

    def __repr__(self) -> str:
        return (
            f'<{self.returncode}>:\n'
            f'{self.stderr}\n'
            f'{self.stdout}\n'
        )

    def __eq__(self, other) -> bool:
        return ((
            self.stdout == other.stdout
        ) and (
            self.stderr == other.stderr
        ) and (
            self.returncode == other.returncode
        ))


class FakeExit(Exception):
    pass


class InterceptSysOutput():

    stdout_text: str
    stderr_text: str
    returncode: int

    def _fake_exit(self, code: int = 0) -> NoReturn:
        self.returncode = code
        raise FakeExit()

    def __init__(self, capture_stdout=True, capture_stderr=False) -> None:
        self.capture_stdout = capture_stdout
        self.capture_stderr = capture_stderr

    def __enter__(self) -> 'InterceptSysOutput':
        self.out_file = tempfile.TemporaryFile('w+', encoding='UTF-8')
        self.err_file = tempfile.TemporaryFile('w+', encoding='UTF-8')
        self.out_file.isatty = lambda: False  # type: ignore
        self.err_file.isatty = lambda: False  # type: ignore

        self._real_stdout = sys.stdout
        self._real_stderr = sys.stderr
        if self.capture_stdout:
            sys.stdout = self.out_file  # type: ignore
        if self.capture_stderr:
            sys.stderr = self.err_file  # type: ignore

        self._real_exit = sys.exit
        sys.exit = self._fake_exit  # type: ignore

        return self

    def __exit__(self, *_exc_details) -> None:
        sys.stdout = self._real_stdout
        sys.stderr = self._real_stderr
        sys.exit = self._real_exit

        self.out_file.flush()
        self.err_file.flush()
        self.out_file.seek(0)
        self.err_file.seek(0)
        self.stdout_text = self.out_file.read()
        self.stderr_text = self.err_file.read()
        self.out_file.close()
        self.err_file.close()


def pikaur(
        cmd: str, capture_stdout=True, capture_stderr=False, fake_makepkg=False
) -> CmdResult:

    PackageDB.discard_local_cache()

    new_args = ['pikaur'] + cmd.split(' ')
    if '-S ' in cmd:
        new_args += [
            '--noconfirm', '--hide-build-log',
        ]
    if fake_makepkg:
        new_args += [
            '--makepkg-path=' + os.path.join(TEST_DIR, 'fake_makepkg')
        ]
        if '--mflags' not in cmd:
            new_args += ['--mflags=--noextract', ]

    print(color_line('\n => ', 10) + ' '.join(new_args))

    intercepted: InterceptSysOutput
    with InterceptSysOutput(
            capture_stderr=capture_stderr,
            capture_stdout=capture_stdout
    ) as _intercepted:
        try:

            # re-parse args:
            sys.argv = new_args
            CachedArgs.args = None  # pylint:disable=protected-access
            parse_args()
            # monkey-patch to force always uncolored output:
            CachedArgs.args.color = 'never'  # type: ignore # pylint:disable=protected-access

            # finally run pikaur's mainloop
            main()

        except FakeExit:
            pass
        intercepted = _intercepted

    PackageDB.discard_local_cache()
    PackageDB.discard_repo_cache()

    return CmdResult(
        returncode=intercepted.returncode,
        stdout=intercepted.stdout_text,
        stderr=intercepted.stderr_text,
    )


def fake_pikaur(cmd_args: str) -> CmdResult:
    return pikaur(cmd_args, fake_makepkg=True)


def pacman(cmd: str) -> CmdResult:
    args = ['pacman'] + cmd.split(' ')
    proc = spawn(args)
    return CmdResult(
        returncode=proc.returncode,
        stdout=proc.stdout_text,
        stderr=proc.stderr_text,
    )


def pkg_is_installed(pkg_name: str) -> bool:
    return pacman(f'-Qi {pkg_name}').returncode == 0


class PikaurTestCase(TestCase):
    # pylint: disable=invalid-name

    separator = color_line(f"\n{'-' * get_term_width()}", 12)

    def run(self, result=None):
        time_started = time()
        log_stderr(self.separator)
        super().run(result)
        print(':: Took {:.2f} seconds'.format(time() - time_started))

    def setUp(self):
        super().setUp()
        log_stderr(self.separator)

    def assertInstalled(self, pkg_name: str) -> None:
        if not pkg_is_installed(pkg_name):
            self.fail(f'Package "{pkg_name}" is not installed.')

    def assertNotInstalled(self, pkg_name: str) -> None:
        self.assertFalse(
            pkg_is_installed(pkg_name)
        )

    def assertProvidedBy(self, dep_name: str, provider_name: str) -> None:
        cmd_result = pacman(f'-Qsq {dep_name}').stdout
        self.assertTrue(
            cmd_result
        )
        self.assertEqual(
            cmd_result.strip(),  # type: ignore
            provider_name
        )


class PikaurDbTestCase(PikaurTestCase):
    """
    tests which are modifying local package DB
    """

    def run(self, result=None):
        if WRITE_DB:
            return super().run(result)
        if result:
            message = 'Not writing to local package DB.'
            if getattr(result, 'getDescription', None):
                message = result.getDescription(self) + f'. {message}'
            result.addSkip(self, message)
        return result

    def remove_packages(self, *pkg_names: str) -> None:
        pikaur('-Rs --noconfirm ' + ' '.join(pkg_names))
        for name in pkg_names:
            self.assertNotInstalled(name)

    def remove_if_installed(self, *pkg_names: str) -> None:
        for pkg_name in pkg_names:
            if pkg_is_installed(pkg_name):
                self.remove_packages(pkg_name)

    def downgrade_repo_pkg(self, repo_pkg_name: str) -> str:
        self.remove_if_installed(repo_pkg_name)
        spawn(f'rm -fr ./{repo_pkg_name}')
        pikaur(f'-G {repo_pkg_name}')
        some_older_commit = spawn(  # type: ignore
            f'git -C ./{repo_pkg_name} log --format=%h'
        ).stdout_text.splitlines()[10]
        spawn(f'git -C ./{repo_pkg_name} checkout {some_older_commit}')
        pikaur(f'-P -i --noconfirm --mflags=--skippgpcheck '
               f'./{repo_pkg_name}/trunk/PKGBUILD')
        self.assertInstalled(repo_pkg_name)
        return PackageDB.get_local_dict()[repo_pkg_name].version

    def downgrade_aur_pkg(self, aur_pkg_name: str, fake_makepkg=False) -> str:
        # and test -P and -G during downgrading :-)
        self.remove_if_installed(aur_pkg_name)
        spawn(f'rm -fr ./{aur_pkg_name}')
        pikaur(f'-G {aur_pkg_name}')
        prev_commit = spawn(  # type: ignore
            f'git -C ./{aur_pkg_name} log --format=%h'
        ).stdout_text.splitlines()[1]
        spawn(f'git -C ./{aur_pkg_name} checkout {prev_commit}')
        pikaur(
            f'-P -i --noconfirm ./{aur_pkg_name}/PKGBUILD',
            fake_makepkg=fake_makepkg
        )
        self.assertInstalled(aur_pkg_name)
        return PackageDB.get_local_dict()[aur_pkg_name].version
