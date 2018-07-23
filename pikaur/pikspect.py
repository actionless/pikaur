""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

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
from time import time, sleep
from typing import List, Dict, TextIO, BinaryIO, Callable, Optional, Union

from .pprint import PrintLock, bold_line
from .threading import handle_exception_in_thread, ThreadSafeBytesStorage
from .pacman import _p


# SMALL_TIMEOUT = 0.1
SMALL_TIMEOUT = 0.01

WRITE_INTERVAL = 0.1


TcAttrsType = List[Union[int, List[bytes]]]


class TTYRestore():

    old_tcattrs = None
    sub_tty_old_tcattrs = None

    @classmethod
    def save(cls):
        if sys.stdin.isatty():
            cls.old_tcattrs = termios.tcgetattr(sys.stdin.fileno())

    @classmethod
    def _restore(cls, what: Optional[TcAttrsType] = None):
        if sys.stdout.isatty():
            # termios.tcdrain(sys.stdout.fileno())
            # if sys.stderr.isatty():
                # termios.tcdrain(sys.stderr.fileno())
            # if sys.stdin.isatty():
                # termios.tcflush(sys.stdin.fileno(), termios.TCIOFLUSH)
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


def _match(pattern, line):
    return len(line) >= len(pattern) and (
        re.compile(pattern).search(line)
        if '.*' in pattern else
        (pattern in line)
    )


class PikspectPopen(subprocess.Popen):  # pylint: disable=too-many-instance-attributes

    print_output: bool
    save_output: bool
    capture_input: bool
    task_id: uuid.UUID
    historic_output: List[bytes]
    pty_in: TextIO
    pty_out: BinaryIO
    default_questions: Dict[str, List[str]]
    max_question_length = 0
    _output_done = False
    # write buffer:
    _write_buffer: bytes = b''
    _last_write: float = 0
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
            for question in questions:
                if len(question) > self.max_question_length:
                    self.max_question_length = len(question)
        self.check_questions()

    def get_output_bytes(self) -> bytes:
        return ThreadSafeBytesStorage.get_bytes_output(self.task_id)

    @handle_exception_in_thread
    def communicator_thread(self) -> int:
        while self.returncode is None:
            sleep(SMALL_TIMEOUT)
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
                        sys.stdout.buffer.write(self._write_buffer)
                        sys.stdout.buffer.flush()
                        self._output_done = True
                        communicate_task.get()
                        pool.join()
                        self.pty_out.close()

    def check_questions(self):
        # pylint: disable=too-many-branches
        try:
            historic_output = b''.join(self.historic_output).decode('utf-8')
        except UnicodeDecodeError:
            return

        clear_buffer = False

        for answer, questions in self.default_questions.items():
            for question in questions:
                if not _match(question, historic_output):
                    continue
                self.write_something((answer + '\n').encode('utf-8'))
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

        if clear_buffer:
            self.historic_output = [b'']

    def write_something(self, output: bytes) -> None:
        if not self.print_output:
            return
        with PrintLock():
            self._write_buffer += output
            if (self._last_write + WRITE_INTERVAL) < time():
                sys.stdout.buffer.write(self._write_buffer)
                sys.stdout.buffer.flush()
                self._write_buffer = b''
                self._last_write = time()

    @handle_exception_in_thread
    def cmd_output_reader_thread(self) -> None:
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
                else:
                    sleep(SMALL_TIMEOUT)
                continue
            pty_reader = readers[0]
            output = pty_reader.read(1)

            self.historic_output = (
                self.historic_output[-self.max_question_length:] + [output, ]
            )
            self.write_something(output)
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
                    sleep(SMALL_TIMEOUT)
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
            self.write_something(char.encode('utf-8'))
            if self.save_output:
                ThreadSafeBytesStorage.add_bytes(self.task_id, char.encode('utf-8'))


# pylint: disable=too-many-locals,too-many-arguments
def pikspect(
        cmd: List[str],
        print_output=True,
        save_output=True,
        auto_proceed=True,
        conflicts: List[List[str]] = None,
        extra_questions: Dict[str, List[str]] = None,
        **kwargs
) -> PikspectPopen:

    # @TODO: refactor to enum or so
    ANSWER_Y = _p("Y")  # pylint: disable=invalid-name
    ANSWER_N = _p("N")  # pylint: disable=invalid-name
    QUESTION_YN_YES = _p("[Y/n]")  # pylint: disable=invalid-name
    QUESTION_YN_NO = _p("[y/N]")  # pylint: disable=invalid-name

    def format_pacman_question(message: str, question=QUESTION_YN_YES) -> str:
        return bold_line(" {} {} ".format(_p(message), question))

    QUESTION_PROCEED = format_pacman_question('Proceed with installation?')  # pylint: disable=invalid-name
    QUESTION_REMOVE = format_pacman_question('Do you want to remove these packages?')  # pylint: disable=invalid-name
    QUESTION_CONFLICT = format_pacman_question(  # pylint: disable=invalid-name
        '%s and %s are in conflict. Remove %s?', QUESTION_YN_NO
    )
    QUESTION_CONFLICT_VIA_PROVIDED = format_pacman_question(  # pylint: disable=invalid-name
        '%s and %s are in conflict (%s). Remove %s?', QUESTION_YN_NO
    )

    def format_conflicts(conflicts: List[List[str]]) -> List[str]:
        return [
            QUESTION_CONFLICT % (new_pkg, old_pkg, old_pkg)
            for new_pkg, old_pkg in conflicts
        ] + [
            (
                re.escape(QUESTION_CONFLICT_VIA_PROVIDED % (new_pkg, old_pkg, '.*', old_pkg))
            ).replace(r"\.\*", ".*")
            for new_pkg, old_pkg in conflicts
        ]

    default_questions: Dict[str, List[str]] = {}
    if auto_proceed:
        default_questions = {
            ANSWER_Y: [
                QUESTION_PROCEED,
                QUESTION_REMOVE,
            ],
            ANSWER_N: [],
        }

    proc = PikspectPopen(
        cmd,
        print_output=print_output,
        save_output=save_output,
        default_questions=default_questions,
        **kwargs
    )

    extra_questions = extra_questions or {}
    if conflicts:
        extra_questions[ANSWER_Y] = extra_questions.get(ANSWER_Y, []) + format_conflicts(conflicts)
    if extra_questions:
        proc.add_answers(extra_questions)

    proc.run()
    return proc


if __name__ == "__main__":
    pikspect(sys.argv[1:])
