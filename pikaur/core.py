"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import subprocess  # nosec B404  # noqa: S404
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from .args import parse_args
from .config import DEFAULT_INPUT_ENCODING
from .pikaprint import ColorsHighlight, color_line, print_stderr

if TYPE_CHECKING:
    # pylint: disable=cyclic-import
    from typing import IO, Final, NotRequired

    from typing_extensions import TypedDict

    IOStream = IO[bytes] | int | None

    class SpawnArgs(TypedDict):
        stdout: NotRequired["IOStream"]
        stderr: NotRequired["IOStream"]
        cwd: NotRequired[str]
        env: NotRequired[dict[str, str]]


PIPE: "Final" = subprocess.PIPE


class InteractiveSpawn(subprocess.Popen[bytes]):

    stdout_text: str | None
    stderr_text: str | None
    _terminated: bool = False

    def communicate(
            self, com_input: bytes | None = None, timeout: float | None = None,
    ) -> tuple[bytes, bytes]:
        if (
                parse_args().print_commands
                and not self._terminated
        ):
            print_stderr(
                color_line("=> ", ColorsHighlight.cyan) +
                (
                    " ".join(str(arg) for arg in self.args)
                    if isinstance(self.args, list) else
                    str(self.args)
                ),
                lock=False,
            )

        stdout, stderr = super().communicate(com_input, timeout)
        self.stdout_text = stdout.decode(DEFAULT_INPUT_ENCODING) if stdout else None
        self.stderr_text = stderr.decode(DEFAULT_INPUT_ENCODING) if stderr else None
        return stdout, stderr

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__} returned {self.returncode}:\n"
            f"STDOUT:\n{self.stdout_text}\n\n"
            f"STDERR:\n{self.stderr_text}"
        )

    def __del__(self) -> None:
        self.terminate()
        self._terminated = True
        self.communicate()


def interactive_spawn(
        cmd: list[str],
        stdout: "IOStream | None" = None,
        stderr: "IOStream | None" = None,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
) -> InteractiveSpawn:
    kwargs: SpawnArgs = {}
    if stdout:
        kwargs["stdout"] = stdout
    if stderr:
        kwargs["stderr"] = stderr
    if cwd:
        kwargs["cwd"] = str(cwd)
    if env:
        kwargs["env"] = env
    process = InteractiveSpawn(
        cmd, **kwargs,
    )
    process.communicate()
    return process


def spawn(
        cmd: list[str],
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
) -> InteractiveSpawn:
    with (
            tempfile.TemporaryFile() as out_file,
            tempfile.TemporaryFile() as err_file,
    ):
        proc = interactive_spawn(
            cmd, stdout=out_file, stderr=err_file,
            cwd=cwd, env=env,
        )
        out_file.seek(0)
        err_file.seek(0)
        proc.stdout_text = out_file.read().decode(DEFAULT_INPUT_ENCODING)
        proc.stderr_text = err_file.read().decode(DEFAULT_INPUT_ENCODING)
    return proc


def joined_spawn(
        cmd: list[str],
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
) -> InteractiveSpawn:
    with tempfile.TemporaryFile() as out_file:
        proc = interactive_spawn(
            cmd, stdout=out_file, stderr=out_file,
            cwd=cwd, env=env,
        )
        out_file.seek(0)
        proc.stdout_text = out_file.read().decode(DEFAULT_INPUT_ENCODING)
    return proc
