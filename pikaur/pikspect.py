"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import fcntl
import os
import re
import select
import shutil
import signal
import struct
import sys
import termios
import tty
from collections.abc import Callable
from os import close, waitpid
from pathlib import Path
from pty import (  # type: ignore[attr-defined]
    CHILD,
    STDIN_FILENO,
    STDOUT_FILENO,
    _read,  # noqa: PLC2701
    fork,
)
from tty import setraw, tcgetattr, tcsetattr  # type: ignore[attr-defined]
from typing import TYPE_CHECKING

from .args import parse_args
from .config import DEFAULT_INPUT_ENCODING
from .i18n import translate
from .logging_extras import create_logger
from .pacman_i18n import _p
from .pikaprint import (
    ColorsHighlight,
    PrintLock,
    TTYRestore,
    color_line,
    get_term_width,
    print_stderr,
)

if TYPE_CHECKING:
    from typing import Any, Final


TcAttrsType = list[int | list[bytes | int]]


logger = create_logger("pikspect", lock=False)


MasterReaderType = Callable[[int], bytes]
StdinReaderType = Callable[[int | None], bytes]


# @TODO: use arg to enable it
FILE_DEBUG: "Final" = False


def file_debug(message: "Any") -> None:
    # @TODO: move it to the logging_extras module
    if FILE_DEBUG:
        with Path("./pikspect_debug.txt").open("a", encoding=DEFAULT_INPUT_ENCODING) as fobj:
            fobj.write(str(message) + "\n")


def _copy(  # pylint: disable=too-many-branches
        master_fd: int,
        master_read: MasterReaderType = _read,
        stdin_read: StdinReaderType = _read,
) -> None:
    """
    Fork of pty._copy from python's stdlib.
    It calls stdin_read even if real stdin is not ready,
    giving the opportunity to inject pre-programmed input there.
    """
    if os.get_blocking(master_fd):
        # If we write more than tty/ndisc is willing to buffer, we may block
        # indefinitely. So we set master_fd to non-blocking temporarily during
        # the copy operation.
        os.set_blocking(master_fd, False)
        try:
            _copy(master_fd, master_read=master_read, stdin_read=stdin_read)
        finally:
            # restore blocking mode for backwards compatibility
            os.set_blocking(master_fd, True)
        return
    high_waterlevel = 4096
    stdin_avail = master_fd != STDIN_FILENO
    stdout_avail = master_fd != STDOUT_FILENO
    i_buf = b""
    o_buf = b""
    while 1:
        rfds: list[int] = []
        wfds: list[int] = []
        if stdin_avail and len(i_buf) < high_waterlevel:
            rfds.append(STDIN_FILENO)
        if stdout_avail and len(o_buf) < high_waterlevel:
            rfds.append(master_fd)
        if stdout_avail and len(o_buf) > 0:
            wfds.append(STDOUT_FILENO)
        if len(i_buf) > 0:
            wfds.append(master_fd)

        rfds, wfds, _xfds = select.select(rfds, wfds, [])

        if STDOUT_FILENO in wfds:
            try:
                written = os.write(STDOUT_FILENO, o_buf)
                o_buf = o_buf[written:]
            except OSError:
                stdout_avail = False

        if master_fd in rfds:
            # Some OSes signal EOF by returning an empty byte string,
            # some throw OSErrors.
            try:
                data = master_read(master_fd)
            except OSError:
                data = b""
            if not data:  # Reached EOF.
                return    # Assume the child process has exited and is unreachable, so we clean up.
            o_buf += data

        if master_fd in wfds:
            written = os.write(master_fd, i_buf)
            i_buf = i_buf[written:]

        if stdin_avail and STDIN_FILENO in rfds:
            data = stdin_read(STDIN_FILENO)
            if not data:
                stdin_avail = False
            else:
                i_buf += data
        # ---- added: ----
        else:
            data = stdin_read(None)
            if data:
                i_buf += data

    file_debug("FDS finished")


def spawn(
        argv: list[str] | str,
        master_read: MasterReaderType = _read,
        stdin_read: StdinReaderType = _read,
        after_fork: Callable[[int, int], None] | None = None,
) -> int:
    """Fork of pty.spawn to add support for `after_fork` callback."""
    if isinstance(argv, str):
        argv = [argv]
    # sys.audit('pty.spawn', argv)

    pid, master_fd = fork()
    if pid == CHILD:
        os.execlp(argv[0], *argv)  # nosec B606  # noqa: S606

    try:
        mode = tcgetattr(STDIN_FILENO)
        setraw(STDIN_FILENO)  # this might break Ctrl+C ?
        restore = True
    # This is the same as termios.error
    except tty.error:  # type: ignore[attr-defined]
        restore = False

    if after_fork:
        after_fork(master_fd, pid)
    try:
        _copy(master_fd, master_read, stdin_read)
    finally:
        if restore:
            tcsetattr(STDIN_FILENO, tty.TCSAFLUSH, mode)  # type: ignore[attr-defined]

        close(master_fd)
    return waitpid(pid, 0)[1]


class ReadlineKeycodes:
    CTRL_C: "Final" = 3
    CTRL_D: "Final" = 4
    CTRL_W: "Final" = 23
    ENTER: "Final" = 13
    BACKSPACE: "Final" = 127


def set_terminal_geometry(file_descriptor: int, rows: int, columns: int) -> None:
    term_geometry_struct = struct.pack("HHHH", rows, columns, 0, 0)
    fcntl.ioctl(
        file_descriptor, termios.TIOCSWINSZ, term_geometry_struct,
    )


class TTYInputWrapper:  # pragma: no cover

    tty_opened = False

    def __init__(self) -> None:
        self.is_pipe = not sys.stdin.isatty()

    def __enter__(self) -> None:
        if self.is_pipe:
            self.old_stdin = sys.stdin
            try:
                logger.debug("Attaching to TTY manually...")
                sys.stdin = Path("/dev/tty").open(encoding=DEFAULT_INPUT_ENCODING)
                self.tty_opened = True
            except Exception as exc:
                logger.debug(exc)

    def __exit__(self, *_exc_details: object) -> None:
        if self.is_pipe and self.tty_opened:
            logger.debug("Restoring stdin...", lock=False)
            sys.stdin.close()
            sys.stdin = self.old_stdin


class NestedTerminal:

    def __init__(self) -> None:
        self.tty_wrapper = TTYInputWrapper()

    def __enter__(self) -> os.terminal_size:
        logger.debug("Opening virtual terminal...")
        self.tty_wrapper.__enter__()
        real_term_geometry = shutil.get_terminal_size((80, 80))
        for stream in (
                sys.stdin,
                sys.stderr,
                sys.stdout,
        ):
            if stream.isatty():
                tty.setcbreak(stream.fileno())
        return real_term_geometry

    def __exit__(self, *exc_details: object) -> None:
        self.tty_wrapper.__exit__(*exc_details)
        TTYRestore.restore()


RECOGNIZED_REGEX_SEQUENCES: "Final[tuple[str]]" = (".*", )


def _match(pattern: str, line: str) -> bool:
    return len(line) >= len(pattern) and bool(
        re.compile(pattern).search(line)
        if max(sequence in pattern for sequence in RECOGNIZED_REGEX_SEQUENCES) else
        (pattern in line),
    )


class PikspectSignalHandler:
    """
    Because Python allows to handle signals only from the main thread
    this class serves as singleton storage to set signal handler
    from within child threads.
    """

    signal_handler: "Callable[..., Any] | None" = None

    @classmethod
    def set_handler(cls, signal_handler: "Callable[..., Any]") -> None:
        cls.signal_handler = signal_handler

    @classmethod
    def clear(cls) -> None:
        cls.signal_handler = None

    @classmethod
    def get(cls) -> "Callable[..., Any] | None":
        return cls.signal_handler


class PikspectPopen:

    historic_output: list[bytes]
    default_questions: dict[str, list[str]]
    # max_question_length = 0  # preserve enough information to analyze questions
    max_question_length = get_term_width() * 2  # preserve also at least last line
    next_answers: list[str]
    pid: int | None = None
    returncode: int | None = None
    real_term_geometry: os.terminal_size | None = None

    capture_output: bool
    output: bytes

    def __enter__(self) -> "PikspectPopen":
        return self

    def __exit__(self, *exc_details: object) -> None:
        logger.debug("Exit details: {}", exc_details)

    def __init__(
            self,
            args: list[str],
            *,
            capture_output: bool = False,
            default_questions: dict[str, list[str]] | None = None,
    ) -> None:
        self.capture_output = capture_output
        self.output = b""

        self.next_answers = []
        self.args = args
        self.default_questions = {}
        self.historic_output = []
        if default_questions:
            self.add_answers(default_questions)

    def add_answers(self, extra_questions: dict[str, list[str]]) -> None:
        for answer, questions in extra_questions.items():
            self.default_questions[answer] = self.default_questions.get(answer, []) + questions
            for question in questions:
                if len(question) > self.max_question_length:
                    self.max_question_length = len(question.encode(DEFAULT_INPUT_ENCODING))
        self.check_questions()

    def send_signal(self, sig: int) -> None:
        file_debug(f"::: ::: TRYING TO HANDLE SIGNAL {sig} FOR PID {self.pid} ::: :::")
        if self.pid:
            os.kill(self.pid, sig)

    def _pty_init(self, file_descriptor: int, pid: int) -> None:
        # @TODO: add support for sigwinch later
        logger.debug("fd: {}, pid: {}", file_descriptor, pid)
        if self.real_term_geometry:
            set_terminal_geometry(
                file_descriptor,
                columns=self.real_term_geometry.columns,
                rows=self.real_term_geometry.lines,
            )
        self.pid = pid

    def run(self) -> None:
        if not isinstance(self.args, list):
            not_a_list_error = translate(
                "`{var_name}` should be list.",
            ).format(var_name="args")
            raise TypeError(not_a_list_error)
        PikspectSignalHandler.set_handler(
            lambda *_whatever: self.send_signal(signal.SIGINT),
        )
        try:
            with NestedTerminal() as real_term_geometry:
                self.real_term_geometry = real_term_geometry
                result = spawn(
                    self.args,
                    master_read=self.cmd_output_reader,
                    stdin_read=self.user_input_reader,
                    after_fork=self._pty_init,
                )
                logger.debug("pid {} finished with return code: {}", self.pid, result)
                self.pid = None
                self.returncode = result
        finally:
            PikspectSignalHandler.clear()

    def check_questions(self) -> None:
        file_debug("check_question1:")

        try:
            historic_output = b"".join(self.historic_output).decode(DEFAULT_INPUT_ENCODING)
        except UnicodeDecodeError:  # pragma: no cover
            return

        file_debug("check_question:")
        file_debug(historic_output)

        clear_buffer = False

        for answer, questions in self.default_questions.items():
            for question in questions:
                if not _match(question, historic_output):
                    continue
                logger.debug("Found right answer to `{}`: `{}`", question, answer)
                self.next_answers.append(answer)
                clear_buffer = True
                break

        if clear_buffer:
            self.historic_output = [b""]

    def cmd_output_reader(self, file_descriptor: int) -> bytes:
        if self.real_term_geometry:
            set_terminal_geometry(
                file_descriptor,
                columns=self.real_term_geometry.columns,
                rows=self.real_term_geometry.lines,
            )
        output = os.read(file_descriptor, 4096)
        if self.capture_output:
            self.output += output

        self.historic_output = (
            self.historic_output[-self.max_question_length:] + [output]
        )
        self.check_questions()
        return output

    def user_input_reader(self, file_descriptor: int | None = None) -> bytes:  # pragma: no cover
        if file_descriptor and self.real_term_geometry:
            set_terminal_geometry(
                file_descriptor,
                columns=self.real_term_geometry.columns,
                rows=self.real_term_geometry.lines,
            )
        file_debug(f"UserInputReader {file_descriptor}:")
        if self.next_answers:
            char = ("\n".join(self.next_answers) + "\n").encode(DEFAULT_INPUT_ENCODING)
            self.next_answers = []
        elif file_descriptor is not None:
            char = os.read(file_descriptor, 1)
        else:
            return b""

        file_debug(char)

        try:
            with PrintLock():
                if len(char) == 1:
                    if ord(char) == ReadlineKeycodes.BACKSPACE:
                        sys.stdout.write("\b \b")
                    elif ord(char) == ReadlineKeycodes.CTRL_W:
                        sys.stdout.write(
                            "\r" + " " * get_term_width() + "\r" +
                            b"".join(
                                self.historic_output,
                            ).decode(DEFAULT_INPUT_ENCODING).splitlines()[-1],
                        )
        except ValueError as exc:
            print(exc)  # noqa: T201
        return char


class YesNo:
    ANSWER_Y = _p("Y")
    ANSWER_N = _p("N")
    QUESTION_YN_YES = _p("[Y/n]")
    QUESTION_YN_NO = _p("[y/N]")


def format_pacman_question(message: str, question: str = YesNo.QUESTION_YN_YES) -> str:
    return f"{_p(message)} {question}"


def pikspect(
        cmd: list[str],
        *,
        auto_proceed: bool = True,
        conflicts: list[list[str]] | None = None,
        extra_questions: dict[str, list[str]] | None = None,
        capture_output: bool | None = None,
) -> PikspectPopen:

    questions_proceed: Final[list[str]] = [
        format_pacman_question("Proceed with installation?"),
        format_pacman_question("Proceed with download?"),
    ]
    questions_remove = [
        format_pacman_question("Do you want to remove these packages?"),
    ]
    questions_conflict = format_pacman_question(
        "%s and %s are in conflict. Remove %s?", YesNo.QUESTION_YN_NO,
    )
    questions_conflict_via_provided = format_pacman_question(
        "%s and %s are in conflict (%s). Remove %s?", YesNo.QUESTION_YN_NO,
    )

    def format_conflicts(conflicts: list[list[str]]) -> list[str]:
        return [
            questions_conflict % (new_pkg, old_pkg, old_pkg)
            for new_pkg, old_pkg in conflicts
        ] + [
            (
                re.escape(questions_conflict_via_provided % (
                    new_pkg, old_pkg, ".*", old_pkg,
                ))
            ).replace(r"\.\*", ".*")
            for new_pkg, old_pkg in conflicts
        ]

    default_questions: dict[str, list[str]] = {}
    if auto_proceed:
        default_questions = {
            YesNo.ANSWER_Y: questions_proceed + questions_remove,
            YesNo.ANSWER_N: [],
        }

    with PikspectPopen(
        cmd,
        default_questions=default_questions,
        capture_output=bool(capture_output),
    ) as proc:

        extra_questions = extra_questions or {}
        if conflicts:
            extra_questions[YesNo.ANSWER_Y] = (
                extra_questions.get(YesNo.ANSWER_Y, []) + format_conflicts(conflicts)
            )
        if extra_questions:
            proc.add_answers(extra_questions)

        if parse_args().print_commands:
            print_stderr(
                color_line("pikspect => ", ColorsHighlight.cyan) +
                " ".join(cmd),
            )
        proc.run()
        return proc


if __name__ == "__main__":
    pikspect(sys.argv[1:])
