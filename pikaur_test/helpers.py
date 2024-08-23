"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import contextlib
import os
import sys
import tempfile
import traceback
from pathlib import Path
from time import time
from typing import TYPE_CHECKING
from unittest import TestCase, mock
from unittest.runner import TextTestResult

from pycman.config import PacmanConfig

from pikaur.args import CachedArgs, parse_args
from pikaur.config import DEFAULT_INPUT_ENCODING
from pikaur.main import main
from pikaur.makepkg_config import MakePkgCommand
from pikaur.pacman import PackageDB
from pikaur.pikaprint import color_line, get_term_width
from pikaur.spawn import InteractiveSpawn
from pikaur.spawn import spawn as core_spawn
from pikaur.srcinfo import SrcInfo

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from subprocess import Popen  # nosec B404
    from typing import Any, NoReturn
    from unittest import TestResult


WRITE_DB: bool = bool(os.environ.get("WRITE_DB"))


if WRITE_DB:
    # pylint:disable=protected-access
    import shutil

    from pikaur.config import ConfigPath, PikaurConfig

    CONFIG_PATH = ConfigPath()
    if CONFIG_PATH.exists():
        shutil.copy(CONFIG_PATH, f"{CONFIG_PATH}.pikaur_test_bak")
        CONFIG_PATH.unlink()
    PikaurConfig._config = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from typing import IO

    from mypy_extensions import DefaultArg


TEST_DIR: Path = Path(os.path.realpath(__file__)).parent


def spawn(cmd: str | list[str], env: dict[str, str] | None = None) -> InteractiveSpawn:
    if isinstance(cmd, str):
        cmd = cmd.split(" ")
    return core_spawn(cmd, env=env)


def log_stderr(line: str) -> None:
    if getattr(sys.stderr, "buffer", None):
        sys.stderr.buffer.write((line + "\n").encode("utf-8"))
        sys.stderr.buffer.flush()
    else:
        sys.stderr.write(line + "\n")
        sys.stderr.flush()


class CmdResult:

    stdout: str
    stderr: str

    def __init__(
            self,
            returncode: int | None = None,
            stdout: str | None = None,
            stderr: str | None = None,
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout or ""
        self.stderr = stderr or ""

    def __repr__(self) -> str:
        return (
            f"<{self.returncode}>:\n"
            f"{self.stderr}\n"
            f"{self.stdout}\n"
        )

    def __hash__(self) -> int:
        return hash(repr(self))

    def __eq__(self, other: "CmdResult") -> bool:  # type: ignore[override]
        return hash(self) == hash(other)


class FakeExit(Exception):  # noqa: N818
    pass


class InterceptSysOutput:

    stdout_text: str
    stderr_text: str
    returncode: int | None = None

    _exited = False

    _patcher_stdout: "mock._patch[IO[str]] | None" = None
    _patcher_stderr: "mock._patch[IO[str]] | None" = None
    _patcher_exit: "mock._patch[Callable[[DefaultArg(int, 'code')], NoReturn]]"  # noqa: F821,RUF100
    _patcher_spawn: "mock._patch[Callable[[list[str]], Popen[bytes]]]"
    patchers: "Sequence[mock._patch[Any] | None] | None" = None

    def _fake_exit(self, code: int = 0) -> "NoReturn":
        self.returncode = code
        raise FakeExit

    def __init__(self, *, capture_stdout: bool = True, capture_stderr: bool = False) -> None:
        self.capture_stdout = capture_stdout
        self.capture_stderr = capture_stderr

        self.out_file = out_file = tempfile.TemporaryFile("w+", encoding="UTF-8")  # noqa: SIM115
        self.err_file = err_file = tempfile.TemporaryFile("w+", encoding="UTF-8")  # noqa: SIM115
        self.out_file.isatty = lambda: False  # type: ignore[method-assign]
        self.err_file.isatty = lambda: False  # type: ignore[method-assign]

        class PrintInteractiveSpawn(InteractiveSpawn):
            def __init__(self, *args: "Any", **kwargs: "Any") -> None:
                kwargs.setdefault("stdout", out_file)
                kwargs.setdefault("stderr", err_file)
                super().__init__(*args, **kwargs)

        if self.capture_stdout:
            self._patcher_stdout = mock.patch("sys.stdout", new=self.out_file)
        if self.capture_stderr:
            self._patcher_stderr = mock.patch("sys.stderr", new=self.err_file)
        self._patcher_exit = mock.patch("sys.exit", new=self._fake_exit)
        self._patcher_spawn = mock.patch("pikaur.spawn.InteractiveSpawn", new=PrintInteractiveSpawn)

        self.patchers = [
            self._patcher_stdout,
            self._patcher_stderr,
            self._patcher_exit,
            self._patcher_spawn,
        ]

    def __enter__(self) -> "InterceptSysOutput":
        for patcher in self.patchers or []:
            if patcher:
                patcher.start()
        return self

    def __exit__(self, *_exc_details: object) -> None:
        if self._exited:
            return
        for patcher in self.patchers or []:
            if patcher:
                patcher.stop()

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
        *,
        capture_stdout: bool = True, capture_stderr: bool = False,
        fake_makepkg: bool = False, skippgpcheck: bool = False,
        print_on_fails: bool = True, fake_makepkg_noextract: bool = True,
) -> CmdResult:

    PackageDB.discard_local_cache()

    new_args = ["pikaur", *cmd.split(" ")]
    mflags = []

    if "-S " in cmd or "-P" in cmd:
        new_args += [
            "--noconfirm",
        ]
    if "-S" in cmd or "-P" in cmd:
        new_args += [
            "--privilege-escalation-target=pacman",
        ]
    if fake_makepkg:
        new_args += [
            "--makepkg-path=" + str(TEST_DIR / "fake_makepkg"),
        ]
        if fake_makepkg_noextract:
            mflags.append("--noextract")
    if skippgpcheck:
        mflags.append("--skippgpcheck")
    if "--mflags" in cmd:
        for arg in new_args[::]:
            if arg.startswith("--mflags"):
                mflags.extend(
                    mflag
                    for mflag in arg.split("=", maxsplit=1)[1].split(",")
                )
                new_args.remove(arg)
                break
    if mflags:
        new_args += [f"--mflags={','.join(mflags)}"]

    log_stderr(color_line("\n => ", 10, force=True) + " ".join(new_args))

    try:
        with (
                InterceptSysOutput(
                    capture_stderr=capture_stderr,
                    capture_stdout=capture_stdout,
                ) as intercepted,
                contextlib.suppress(FakeExit),
        ):
            # re-parse args:
            CachedArgs.args = None
            MakePkgCommand._cmd = None  # pylint: disable=protected-access
            with mock.patch("sys.argv", new=new_args):
                parse_args()
            # monkey-patch to force always uncolored output:
            CachedArgs.args.color = "never"  # type: ignore[attr-defined]
            # finally run pikaur's main loop
            main(embed=True)
    except Exception as exc:
        log_stderr(str(exc))
        log_stderr(traceback.format_exc())

    PackageDB.discard_local_cache()
    PackageDB.discard_repo_cache()

    result = CmdResult(
        returncode=intercepted.returncode,
        stdout=intercepted.stdout_text,
        stderr=intercepted.stderr_text,
    )
    if print_on_fails and (intercepted.returncode != 0):
        log_stderr(str(result))
    return result


def fake_pikaur(cmd_args: str) -> CmdResult:
    return pikaur(cmd_args, fake_makepkg=True)


def pacman(cmd: str) -> CmdResult:
    args = ["pacman", *cmd.split(" ")]
    proc = spawn(args)
    return CmdResult(
        returncode=proc.returncode,
        stdout=proc.stdout_text,
        stderr=proc.stderr_text,
    )


def pkg_is_installed(pkg_name: str) -> bool:
    return pkg_name in [
        pkg.name for pkg in
        PacmanConfig(conf="/etc/pacman.conf").initialize_alpm().get_localdb().search(pkg_name)
    ]


class PikaurTestCase(TestCase):
    # pylint: disable=invalid-name

    separator = color_line(f"\n{'-' * get_term_width()}", 12, force=True)

    def run(self, result: "TestResult | None" = None) -> "TestResult | None":
        time_started = time()
        log_stderr(self.separator)
        result = super().run(result)
        # print(result and result.collectedDurations)
        time_spent = time() - time_started
        log_stderr(f":: Took {(time_spent):.2f} seconds")
        if test_times_path := os.environ.get("TEST_TIMES_PATH"):
            with Path(test_times_path).open("a", encoding=DEFAULT_INPUT_ENCODING) as fobj:
                fobj.write(f"{(time_spent):.2f} {self}\n")
        return result

    def setUp(self) -> None:
        super().setUp()
        log_stderr(self.separator)

    def assertInstalled(self, pkg_name: str) -> None:  # noqa: N802
        if not pkg_is_installed(pkg_name):
            self.fail(f'Package "{pkg_name}" is not installed.')

    def assertNotInstalled(self, pkg_name: str) -> None:  # noqa: N802
        if pkg_is_installed(pkg_name):
            self.fail(f'Package "{pkg_name}" is still installed.')

    def assertProvidedBy(self, dep_name: str, provider_name: str) -> None:  # noqa: N802
        cmd_result: str = pacman(f"-Qiq {dep_name}").stdout
        self.assertTrue(
            cmd_result,
        )
        self.assertEqual(
            cmd_result.splitlines()[0].split(":")[1].strip(),
            provider_name,
        )


class PikaurDbTestCase(PikaurTestCase):
    """Tests which are modifying local package DB."""

    def run(self, result: "TestResult | None" = None) -> "TestResult | None":
        if WRITE_DB:
            return super().run(result)
        if result:
            message = "Not writing to local package DB (env `WRITE_DB`)."
            if isinstance(result, TextTestResult):
                message = result.getDescription(self) + f". {message}"
            result.addSkip(self, message)
        return result

    def remove_packages(self, *pkg_names: str) -> None:
        pikaur("-Rs --noconfirm " + " ".join(pkg_names))
        for name in pkg_names:
            self.assertNotInstalled(name)

    def remove_if_installed(self, *pkg_names: str) -> None:
        for pkg_name in pkg_names:
            if pkg_is_installed(pkg_name):
                self.remove_packages(pkg_name)

    @staticmethod
    def _checkout_older_version(
            repo_dir: str,
            build_dir: str,
            pkg_name: str,
            count: int,
            to_version: str | None,
    ) -> None:
        if count < 1:
            wrong_count_msg = "Count of commits to downgrade should be a positive number."
            raise RuntimeError(wrong_count_msg)
        srcinfo = SrcInfo(build_dir, pkg_name)
        srcinfo.regenerate()
        from_version = srcinfo.get_version()
        if not to_version:
            proc = spawn(
                f"git -C {repo_dir} log --format=%h",
            )
            if not proc.stdout_text:
                raise RuntimeError
            some_older_commit = proc.stdout_text.splitlines()[count]
            spawn(f"git -C {repo_dir} checkout {some_older_commit}")
            srcinfo.regenerate()
            to_version = srcinfo.get_version()
        else:
            current_version = srcinfo.get_version()
            count = 1
            while current_version != to_version:
                proc = spawn(
                    f"git -C {repo_dir} log --format=%h",
                )
                if not proc.stdout_text:
                    raise RuntimeError
                some_older_commit = proc.stdout_text.splitlines()[count]
                spawn(f"git -C {repo_dir} checkout {some_older_commit}")
                srcinfo.regenerate()
                current_version = srcinfo.get_version()
                log_stderr(current_version)
                count += 1
        log_stderr(f"Downgrading from {from_version} to {to_version}...")

    def downgrade_repo_pkg(
            self,
            repo_pkg_name: str,
            *,
            fake_makepkg: bool = False,
            skippgpcheck: bool = False,
            count: int = 10,
            build_root: str = ".",
            remove_before_upgrade: bool = True,
            to_version: str | None = None,
    ) -> str:
        if remove_before_upgrade:
            self.remove_if_installed(repo_pkg_name)
        spawn(f"rm -fr {build_root}/{repo_pkg_name}")
        pikaur(f"-G {repo_pkg_name}")
        repo_dir = f"{build_root}/{repo_pkg_name}/"
        build_dir = f"{repo_dir}/"
        self._checkout_older_version(
            build_dir=build_dir,
            repo_dir=repo_dir,
            pkg_name=repo_pkg_name,
            count=count,
            to_version=to_version,
        )
        pikaur(
            "-P -i --noconfirm "
            f"{build_dir}/PKGBUILD",
            fake_makepkg=fake_makepkg,
            skippgpcheck=skippgpcheck,
        )
        self.assertInstalled(repo_pkg_name)
        return PackageDB.get_local_dict()[repo_pkg_name].version

    def downgrade_aur_pkg(
            self, aur_pkg_name: str,
            *,
            fake_makepkg: bool = False,
            skippgpcheck: bool = False,
            count: int = 1,
            build_root: str = ".",
            remove_before_upgrade: bool = True,
            to_version: str | None = None,
    ) -> str:
        # and test -P and -G during downgrading :-)
        old_version = (
            PackageDB.get_local_dict()[aur_pkg_name].version
            if aur_pkg_name in PackageDB.get_local_pkgnames()
            else None
        )
        if remove_before_upgrade:
            self.remove_if_installed(aur_pkg_name)
        build_dir = f"{build_root}/{aur_pkg_name}"
        spawn(f"rm -fr {build_dir}")
        pikaur(f"-G {aur_pkg_name}")
        self._checkout_older_version(
            build_dir=build_dir,
            repo_dir=build_dir,
            pkg_name=aur_pkg_name,
            count=count,
            to_version=to_version,
        )
        pikaur(
            "-P -i --noconfirm "
            f"{build_dir}/PKGBUILD",
            fake_makepkg=fake_makepkg,
            skippgpcheck=skippgpcheck,
        )
        self.assertInstalled(aur_pkg_name)
        new_version = PackageDB.get_local_dict()[aur_pkg_name].version
        self.assertNotEqual(
            old_version, new_version,
            f"After downgrading version of {aur_pkg_name} still stays on {old_version}",
        )
        return new_version
