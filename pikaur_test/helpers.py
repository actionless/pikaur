""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import sys
import os
import tempfile
from time import time
from unittest import TestCase
from typing import Optional, List, NoReturn, Union

from pycman.config import PacmanConfig

# pylint:disable=no-name-in-module

from pikaur.main import main
from pikaur.args import CachedArgs, parse_args
from pikaur.pacman import PackageDB
from pikaur.pprint import get_term_width, color_line
from pikaur.makepkg_config import MakePkgCommand
from pikaur.core import spawn as core_spawn, InteractiveSpawn


TEST_DIR = os.path.dirname(os.path.realpath(__file__))


WRITE_DB = bool(os.environ.get('WRITE_DB'))


if WRITE_DB:
    # pylint:disable=protected-access
    from pikaur.config import CONFIG_PATH, PikaurConfig
    if os.path.exists(CONFIG_PATH):
        os.unlink(CONFIG_PATH)
    PikaurConfig._config = None  # type: ignore


def spawn(cmd: Union[str, List[str]], **kwargs) -> InteractiveSpawn:
    if isinstance(cmd, str):
        cmd = cmd.split(' ')
    return core_spawn(cmd, **kwargs)


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

    _exited = False

    def _fake_exit(self, code: int = 0) -> NoReturn:
        self.returncode = code
        raise FakeExit()

    def __init__(self, capture_stdout=True, capture_stderr=False) -> None:
        self.capture_stdout = capture_stdout
        self.capture_stderr = capture_stderr

    def __enter__(self) -> 'InterceptSysOutput':
        self.out_file = tempfile.TemporaryFile('w+', encoding='UTF-8')  # pylint: disable=consider-using-with
        self.err_file = tempfile.TemporaryFile('w+', encoding='UTF-8')  # pylint: disable=consider-using-with
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
        if self._exited:
            return
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

        self._exited = True

    def __del__(self):
        self.__exit__()


def pikaur(
        cmd: str, capture_stdout=True, capture_stderr=False,
        fake_makepkg=False, skippgpcheck=False
) -> CmdResult:

    PackageDB.discard_local_cache()

    new_args = ['pikaur'] + cmd.split(' ')
    mflags = []

    if '-S ' in cmd:
        new_args += [
            '--noconfirm',
        ]
    if fake_makepkg:
        new_args += [
            '--makepkg-path=' + os.path.join(TEST_DIR, 'fake_makepkg')
        ]
        mflags.append('--noextract')
    if skippgpcheck:
        mflags.append('--skippgpcheck')
    if '--mflags' in cmd:
        for arg in new_args[::]:
            if arg.startswith('--mflags'):
                for mflag in arg.split('=', maxsplit=1)[1].split(','):
                    mflags.append(mflag)
                new_args.remove(arg)
                break
    if mflags:
        new_args += [f"--mflags={','.join(mflags)}", ]

    print(color_line('\n => ', 10, force=True) + ' '.join(new_args))

    intercepted: InterceptSysOutput
    with InterceptSysOutput(
            capture_stderr=capture_stderr,
            capture_stdout=capture_stdout
    ) as _intercepted:
        try:

            # re-parse args:
            sys.argv = new_args
            CachedArgs.args = None  # pylint:disable=protected-access
            MakePkgCommand._cmd = None  # pylint:disable=protected-access
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
    return pkg_name in [
        pkg.name for pkg in
        PacmanConfig(conf='/etc/pacman.conf').initialize_alpm().get_localdb().search(pkg_name)
    ]


class PikaurTestCase(TestCase):
    # pylint: disable=invalid-name

    separator = color_line(f"\n{'-' * get_term_width()}", 12, force=True)

    def run(self, result=None):
        time_started = time()
        log_stderr(self.separator)
        super().run(result)
        print(':: Took {:.2f} seconds'.format(time() - time_started))  # pylint: disable=consider-using-f-string

    def setUp(self):
        super().setUp()
        log_stderr(self.separator)

    def assertInstalled(self, pkg_name: str) -> None:
        if not pkg_is_installed(pkg_name):
            self.fail(f'Package "{pkg_name}" is not installed.')

    def assertNotInstalled(self, pkg_name: str) -> None:
        if pkg_is_installed(pkg_name):
            self.fail(f'Package "{pkg_name}" is still installed.')

    def assertProvidedBy(self, dep_name: str, provider_name: str) -> None:
        cmd_result = pacman(f'-Qiq {dep_name}').stdout
        self.assertTrue(
            cmd_result
        )
        self.assertEqual(
            cmd_result.splitlines()[0].split(':')[1].strip(),  # type: ignore
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

    def downgrade_repo_pkg(
            self, repo_pkg_name: str,
            fake_makepkg=False, skippgpcheck=False,
            count=10
    ) -> str:
        self.remove_if_installed(repo_pkg_name)
        spawn(f'rm -fr ./{repo_pkg_name}')
        pikaur(f'-G {repo_pkg_name}')
        some_older_commit = spawn(
            f'git -C ./{repo_pkg_name} log --format=%h'
        ).stdout_text.splitlines()[count]
        spawn(f'git -C ./{repo_pkg_name} checkout {some_older_commit}')
        pikaur(
            '-P -i --noconfirm '
            f'./{repo_pkg_name}/trunk/PKGBUILD',
            fake_makepkg=fake_makepkg,
            skippgpcheck=skippgpcheck
        )
        self.assertInstalled(repo_pkg_name)
        return PackageDB.get_local_dict()[repo_pkg_name].version

    def downgrade_aur_pkg(
            self, aur_pkg_name: str,
            fake_makepkg=False, skippgpcheck=False,
            count=1
    ) -> str:
        # and test -P and -G during downgrading :-)
        old_version = (
            PackageDB.get_local_dict()[aur_pkg_name].version
            if aur_pkg_name in PackageDB.get_local_pkgnames()
            else None
        )
        self.remove_if_installed(aur_pkg_name)
        spawn(f'rm -fr ./{aur_pkg_name}')
        pikaur(f'-G {aur_pkg_name}')
        prev_commit = spawn(
            f'git -C ./{aur_pkg_name} log --format=%h'
        ).stdout_text.splitlines()[count]
        spawn(f'git -C ./{aur_pkg_name} checkout {prev_commit}')
        pikaur(
            '-P -i --noconfirm '
            f'./{aur_pkg_name}/PKGBUILD',
            fake_makepkg=fake_makepkg,
            skippgpcheck=skippgpcheck
        )
        self.assertInstalled(aur_pkg_name)
        new_version = PackageDB.get_local_dict()[aur_pkg_name].version
        self.assertNotEqual(
            old_version, new_version,
            f"After downgrading version of {aur_pkg_name} still stays on {old_version}"
        )
        return new_version
