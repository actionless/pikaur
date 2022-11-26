"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import os
import sys
import tempfile
from time import time
from typing import Any, NoReturn
from unittest import TestCase, TestResult
from unittest.runner import TextTestResult

from pycman.config import PacmanConfig

import pikaur as pikaur_module
from pikaur.args import CachedArgs, parse_args
from pikaur.core import InteractiveSpawn
from pikaur.core import spawn as core_spawn
from pikaur.main import main
from pikaur.makepkg_config import MakePkgCommand
from pikaur.pacman import PackageDB
from pikaur.pprint import color_line, get_term_width
from pikaur.srcinfo import SrcInfo


TEST_DIR = os.path.dirname(os.path.realpath(__file__))


WRITE_DB = bool(os.environ.get('WRITE_DB'))


if WRITE_DB:
    # pylint:disable=protected-access
    from pikaur.config import CONFIG_PATH, PikaurConfig
    if os.path.exists(CONFIG_PATH):
        os.unlink(CONFIG_PATH)
    PikaurConfig._config = None  # type: ignore[assignment]


def spawn(cmd: str | list[str], env: dict[str, str] | None = None) -> InteractiveSpawn:
    if isinstance(cmd, str):
        cmd = cmd.split(' ')
    return core_spawn(cmd, env=env)


def log_stderr(line: str) -> None:
    sys.stderr.buffer.write((line + '\n').encode('utf-8'))
    sys.stderr.buffer.flush()


class CmdResult:

    stdout: str
    stderr: str

    def __init__(
            self,
            returncode: int | None = None,
            stdout: str | None = None,
            stderr: str | None = None
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout or ''
        self.stderr = stderr or ''

    def __repr__(self) -> str:
        return (
            f'<{self.returncode}>:\n'
            f'{self.stderr}\n'
            f'{self.stdout}\n'
        )

    def __eq__(self, other: 'CmdResult') -> bool:  # type: ignore[override]
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

    def __init__(self, capture_stdout: bool = True, capture_stderr: bool = False) -> None:
        self.capture_stdout = capture_stdout
        self.capture_stderr = capture_stderr

    def __enter__(self) -> 'InterceptSysOutput':

        class PrintInteractiveSpawn(InteractiveSpawn):
            def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                kwargs.setdefault('stdout', sys.stdout)
                kwargs.setdefault('stderr', sys.stderr)
                super().__init__(*args, **kwargs)

        self.out_file = tempfile.TemporaryFile('w+', encoding='UTF-8')
        self.err_file = tempfile.TemporaryFile('w+', encoding='UTF-8')
        self.out_file.isatty = lambda: False  # type: ignore[assignment]
        self.err_file.isatty = lambda: False  # type: ignore[assignment]

        self._real_stdout = sys.stdout
        self._real_stderr = sys.stderr
        if self.capture_stdout:
            sys.stdout = self.out_file  # type: ignore[assignment]
        if self.capture_stderr:
            sys.stderr = self.err_file  # type: ignore[assignment]

        self._real_interactive_spawn = InteractiveSpawn
        pikaur_module.core.InteractiveSpawn = PrintInteractiveSpawn  # type: ignore[misc]

        self._real_exit = sys.exit
        sys.exit = self._fake_exit  # type: ignore[assignment]

        return self

    def __exit__(self, *_exc_details: Any) -> None:
        if self._exited:
            return
        sys.stdout = self._real_stdout
        sys.stderr = self._real_stderr
        sys.exit = self._real_exit
        pikaur_module.core.InteractiveSpawn = self._real_interactive_spawn  # type: ignore[misc]

        self.out_file.flush()
        self.err_file.flush()
        self.out_file.seek(0)
        self.err_file.seek(0)
        self.stdout_text = self.out_file.read()
        self.stderr_text = self.err_file.read()
        self.out_file.close()
        self.err_file.close()

        self._exited = True

    def __del__(self) -> None:
        self.__exit__()


def pikaur(
        cmd: str,
        capture_stdout: bool = True, capture_stderr: bool = False,
        fake_makepkg: bool = False, skippgpcheck: bool = False
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
    try:
        with InterceptSysOutput(
                capture_stderr=capture_stderr,
                capture_stdout=capture_stdout
        ) as _intercepted:
            try:

                # re-parse args:
                sys.argv = new_args
                CachedArgs.args = None
                MakePkgCommand._cmd = None  # pylint: disable=protected-access
                parse_args()
                # monkey-patch to force always uncolored output:
                CachedArgs.args.color = 'never'  # type: ignore[attr-defined]

                # finally run pikaur's main loop
                main(embed=True)

            except FakeExit:
                pass
            finally:
                intercepted = _intercepted
    except Exception as exc:
        print(exc)

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

    def run(self, result: TestResult | None = None) -> TestResult | None:
        time_started = time()
        log_stderr(self.separator)
        result = super().run(result)
        # pylint: disable=consider-using-f-string
        print(':: Took {:.2f} seconds'.format(time() - time_started))
        return result

    def setUp(self) -> None:
        super().setUp()
        log_stderr(self.separator)

    def assertInstalled(self, pkg_name: str) -> None:
        if not pkg_is_installed(pkg_name):
            self.fail(f'Package "{pkg_name}" is not installed.')

    def assertNotInstalled(self, pkg_name: str) -> None:
        if pkg_is_installed(pkg_name):
            self.fail(f'Package "{pkg_name}" is still installed.')

    def assertProvidedBy(self, dep_name: str, provider_name: str) -> None:
        cmd_result: str = pacman(f'-Qiq {dep_name}').stdout
        self.assertTrue(
            cmd_result
        )
        self.assertEqual(
            cmd_result.splitlines()[0].split(':')[1].strip(),
            provider_name
        )


class PikaurDbTestCase(PikaurTestCase):
    """
    tests which are modifying local package DB
    """

    def run(self, result: TestResult | None = None) -> TestResult | None:
        if WRITE_DB:
            return super().run(result)
        if result:
            message = 'Not writing to local package DB (env `WRITE_DB`).'
            if isinstance(result, TextTestResult):
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

    def downgrade_repo_pkg(  # pylint: disable=too-many-arguments
            self, repo_pkg_name: str,
            fake_makepkg: bool = False, skippgpcheck: bool = False,
            count: int = 10,
            build_root: str = '.',
            remove_before_upgrade: bool = True,
            to_version: str | None = None,
    ) -> str:
        if remove_before_upgrade:
            self.remove_if_installed(repo_pkg_name)
        spawn(f'rm -fr {build_root}/{repo_pkg_name}')
        pikaur(f'-G {repo_pkg_name}')
        build_dir = f'{build_root}/{repo_pkg_name}/trunk/'
        srcinfo = SrcInfo(build_dir, repo_pkg_name)
        srcinfo.regenerate()
        from_version = srcinfo.get_version()
        if not to_version:
            proc = spawn(
                f'git -C {build_root}/{repo_pkg_name} log --format=%h'
            )
            if not proc.stdout_text:
                raise RuntimeError()
            some_older_commit = proc.stdout_text.splitlines()[count]
            spawn(f'git -C {build_root}/{repo_pkg_name} checkout {some_older_commit}')
            srcinfo.regenerate()
            to_version = srcinfo.get_version()
        else:
            current_version = srcinfo.get_version()
            count = 1
            while current_version != to_version:
                proc = spawn(
                    f'git -C {build_root}/{repo_pkg_name} log --format=%h'
                )
                if not proc.stdout_text:
                    raise RuntimeError()
                some_older_commit = proc.stdout_text.splitlines()[count]
                spawn(f'git -C {build_root}/{repo_pkg_name} checkout {some_older_commit}')
                srcinfo.regenerate()
                current_version = srcinfo.get_version()
                print(current_version)
                count += 1
        print(f"Downgrading from {from_version} to {to_version}...")
        pikaur(
            '-P -i --noconfirm '
            f'{build_dir}/PKGBUILD',
            fake_makepkg=fake_makepkg,
            skippgpcheck=skippgpcheck
        )
        self.assertInstalled(repo_pkg_name)
        return PackageDB.get_local_dict()[repo_pkg_name].version

    def downgrade_aur_pkg(
            self, aur_pkg_name: str,
            fake_makepkg: bool = False, skippgpcheck: bool = False,
            count: int = 1
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
        proc = spawn(
            f'git -C ./{aur_pkg_name} log --format=%h'
        )
        if not proc.stdout_text:
            raise RuntimeError()
        prev_commit = proc.stdout_text.splitlines()[count]
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
