import sys
import subprocess
import tty
import pty
import termios
import select
import shutil
import struct
import fcntl
import uuid
import os
import re
import threading
from multiprocessing.pool import ThreadPool
from time import sleep
from typing import List, Dict, TextIO, BinaryIO, Callable

from .pacman import (
    ANSWER_Y, ANSWER_N, QUESTION_PROCEED, QUESTION_REMOVE,
    format_conflicts,
)
from .pprint import PrintLock, print_stdout, purge_line, go_line_up
from .threading import handle_exception_in_thread, ThreadSafeBytesStorage


Y = ANSWER_Y
N = ANSWER_N


# MAX_QUESTION_LENGTH = 512
MAX_QUESTION_LENGTH = 256


# SMALL_TIMEOUT = 0.1
SMALL_TIMEOUT = 0.01


class TTYRestore():

    old_tcattrs = None
    sub_tty_old_tcattrs = None

    @classmethod
    def save(cls):
        if sys.stdin.isatty():
            cls.old_tcattrs = termios.tcgetattr(sys.stdin.fileno())

    @classmethod
    def _restore(cls, what=None):
        if sys.stderr.isatty():
            termios.tcdrain(sys.stderr.fileno())
        if sys.stdout.isatty():
            termios.tcdrain(sys.stdout.fileno())
        if sys.stdin.isatty():
            termios.tcflush(sys.stdin.fileno(), termios.TCIOFLUSH)
        if what:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, what)

    @classmethod
    def restore(cls, *_whatever):  # pylint:disable=method-hidden
        cls._restore(cls.old_tcattrs)

    def __init__(self):
        self.restore = self.restore_new
        self.sub_tty_old_tcattrs = termios.tcgetattr(sys.stdin.fileno())

    def restore_new(self, *_whatever):
        self._restore(self.sub_tty_old_tcattrs)


TTYRestore.save()


def set_terminal_geometry(file_descriptor: int, rows: int, columns: int) -> None:
    term_geometry_struct = struct.pack("HHHH", rows, columns, 0, 0)
    fcntl.ioctl(file_descriptor, termios.TIOCSWINSZ, term_geometry_struct)


class NestedTerminal():

    def __enter__(self) -> os.terminal_size:
        real_term_geometry = shutil.get_terminal_size((80, 80))
        if sys.stdin.isatty():
            tty.setcbreak(sys.stdin.fileno())
        if sys.stderr.isatty():
            tty.setcbreak(sys.stderr.fileno())
        if sys.stdout.isatty():
            tty.setcbreak(sys.stdout.fileno())
        return real_term_geometry

    def __exit__(self, *_exc_details) -> None:
        TTYRestore.restore()


class PikspectPopen(subprocess.Popen):  # pylint: disable=too-many-instance-attributes

    print_output: bool
    save_output: bool
    capture_input: bool
    task_id: uuid.UUID
    historic_output: List[bytes]
    pty_in: TextIO
    pty_out: BinaryIO
    default_questions: Dict[str, List[str]]
    _hide_after: List[str]
    _show_after: List[str]
    _hide_each_line: List[str]
    _re_cache: Dict[str, int]
    _output_done = False
    # some help for mypy:
    _waitpid_lock: threading.Lock
    _try_wait: Callable
    _handle_exitstatus: Callable

    def __init__(  # pylint: disable=too-many-arguments
            self,
            args: List[str],
            print_output: bool = True,
            save_output: bool = True,
            capture_input: bool = True,
            default_questions: Dict[str, List[str]] = None,
            **kwargs
    ) -> None:
        self.args = args
        self.print_output = print_output
        self.save_output = save_output
        self.capture_input = capture_input
        self.default_questions = {}
        self.historic_output = []
        self._re_cache = {}
        self._hide_after = []
        self._show_after = []
        self._hide_each_line = []
        if default_questions:
            self.add_answers(default_questions)

        self.task_id = uuid.uuid4()
        self.pty_user_master, self.pty_user_slave = pty.openpty()
        self.pty_cmd_master, self.pty_cmd_slave = pty.openpty()

        super().__init__(
            args=args,
            stdin=self.pty_user_slave,
            stdout=self.pty_cmd_slave,
            stderr=self.pty_cmd_slave,
            **kwargs
        )

    def add_answers(self, extra_questions: Dict[str, List[str]]) -> None:
        for answer, questions in extra_questions.items():
            self.default_questions[answer] = self.default_questions.get(answer, []) + questions
        self.check_questions()

    def get_output_bytes(self) -> bytes:
        return ThreadSafeBytesStorage.get_bytes_output(self.task_id)

    def get_output(self) -> str:
        return self.get_output_bytes().decode('utf-8')

    def wait_for_output(self, pattern: str = None, text: str = None) -> bool:
        if text:
            pattern = re.escape(text)
        compiled = self._re_compile(pattern)
        while self.returncode is None:
            try:
                historic_output = b''.join(self.historic_output).decode('utf-8')
            except UnicodeDecodeError:
                continue
            if compiled.search(historic_output):
                return True
            sleep(SMALL_TIMEOUT)
        return False

    def hide_after(self, pattern):
        self._hide_after.append(pattern)
        self.check_questions()

    def show_after(self, pattern):
        self._show_after.append(pattern)
        self.check_questions()

    def hide_each_line(self, pattern):
        self._hide_each_line.append(pattern)
        self.check_questions()

    @handle_exception_in_thread
    def communicator_thread(self) -> int:
        while self.returncode is None:
            with self._waitpid_lock:
                if self.returncode is not None:
                    break  # Another thread waited.
                (pid, sts) = self._try_wait(0)
                if pid == self.pid and self._output_done:
                    self._handle_exitstatus(sts)
        return self.returncode

    def run(self) -> None:
        with NestedTerminal() as real_term_geometry:
            if 'sudo' in self.args:
                subprocess.run(['sudo', '-v'])
            with open(self.pty_user_master, 'w') as self.pty_in:
                with open(self.pty_cmd_master, 'rb', buffering=0) as self.pty_out:
                    set_terminal_geometry(
                        self.pty_out.fileno(),
                        columns=real_term_geometry.columns,
                        rows=real_term_geometry.lines
                    )
                    with ThreadPool(processes=3) as pool:
                        output_task = pool.apply_async(self.cmd_output_reader_thread, ())
                        pool.apply_async(self.user_input_reader_thread, ())
                        communicate_task = pool.apply_async(self.communicator_thread, ())
                        pool.close()

                        output_task.get()
                        self._output_done = True
                        communicate_task.get()
                        pool.join()
                        self.pty_out.close()

    def _re_compile(self, pattern):
        if not self._re_cache.get(pattern):
            self._re_cache[pattern] = re.compile(pattern)
        return self._re_cache[pattern]

    def _match(self, pattern, line):
        return len(line) >= len(pattern) and (
            self._re_compile(pattern).search(line)
            if '.*' in pattern else
            (pattern in line)
        )

    def check_questions(self):
        # pylint: disable=too-many-branches
        try:
            historic_output = b''.join(self.historic_output).decode('utf-8')
        except UnicodeDecodeError:
            return

        clear_buffer = False

        for pattern in self._hide_each_line:
            if self._match(pattern, historic_output):
                purge_line()
                if historic_output[-1] == '\n':
                    go_line_up()
                    clear_buffer = True

        for pattern in self._hide_after[:]:
            if self._match(pattern, historic_output):
                self.print_output = False
                self.capture_input = False
                self._hide_after.remove(pattern)
                purge_line()
                clear_buffer = True

        for answer, questions in self.default_questions.items():
            for question in questions:
                if not self._match(question, historic_output):
                    continue
                if self.print_output:
                    print_stdout(answer)
                with PrintLock():
                    if self.save_output:
                        ThreadSafeBytesStorage.add_bytes(
                            self.task_id, answer.encode('utf-8') + b'\n'
                        )
                    self.pty_in.write(answer)
                    sleep(SMALL_TIMEOUT)
                    self.pty_in.write('\n')
                    self.pty_in.flush()
                clear_buffer = True
                break

        for pattern in self._show_after[:]:
            if self._match(pattern, historic_output):
                self.print_output = True
                self.capture_input = True
                self._show_after.remove(pattern)

        if clear_buffer:
            self.historic_output = [b'']

    @handle_exception_in_thread
    def cmd_output_reader_thread(self) -> None:
        max_question_length = MAX_QUESTION_LENGTH
        while True:

            try:
                selected = select.select([self.pty_out, ], [], [], SMALL_TIMEOUT)
            except ValueError:
                return
            else:
                readers = selected[0]
            if not readers:
                if self.returncode is not None:
                    break
                if self.historic_output:
                    self._output_done = True
                    sleep(SMALL_TIMEOUT)
                continue
            pty_reader = readers[0]
            output = pty_reader.read(1)

            self.historic_output = (
                self.historic_output[-max_question_length:] + [output, ]
            )
            if self.print_output:
                with PrintLock():
                    sys.stdout.buffer.write(output)
                    sys.stdout.buffer.flush()
            if self.save_output:
                ThreadSafeBytesStorage.add_bytes(self.task_id, output)
            self.check_questions()

    @handle_exception_in_thread
    def user_input_reader_thread(self) -> None:
        while self.returncode is None:
            if not self.capture_input:
                sleep(SMALL_TIMEOUT)
                continue

            char = None

            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                line = sys.stdin.read(1)
                if line:
                    char = line
                else:
                    continue
            else:
                sleep(SMALL_TIMEOUT)
                continue

            try:
                with PrintLock():
                    self.pty_in.write(char)
                    self.pty_in.flush()
            except ValueError as exc:
                print(exc)
            if self.print_output:
                print_stdout(char, end='', flush=True)
            if self.save_output:
                ThreadSafeBytesStorage.add_bytes(self.task_id, char.encode('utf-8'))


# pylint: disable=too-many-locals,too-many-arguments
def pikspect(
        cmd: List[str],
        print_output=True,
        save_output=True,
        conflicts: List[List[str]] = None,
        extra_questions: Dict[str, List[str]] = None,
        **kwargs
) -> PikspectPopen:
    extra_questions = extra_questions or {}
    if conflicts:
        extra_questions[Y] = extra_questions.get(Y, []) + format_conflicts(conflicts)

    default_questions: Dict[str, List[str]] = {
        Y: [
            QUESTION_PROCEED,
            QUESTION_REMOVE,
        ],
        N: [],
    }

    proc = PikspectPopen(
        cmd,
        print_output=print_output,
        save_output=save_output,
        default_questions=default_questions,
        **kwargs
    )
    if extra_questions:
        proc.add_answers(extra_questions)
    proc.run()

    return proc


if __name__ == "__main__":
    pikspect(sys.argv[1:])
