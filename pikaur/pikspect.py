import sys
import subprocess
import tty
import pty
import traceback
import gettext
import io
import termios
import select
from multiprocessing.pool import ThreadPool
from typing import List, Tuple, Callable, Any
from threading import Lock
from time import sleep

from .core import isolate_root_cmd
from .pprint import bold_line

PACMAN_TRANSLATION = gettext.translation('pacman', fallback=True)


def _p(msg: str) -> str:
    return PACMAN_TRANSLATION.gettext(msg)


QUESTION_MESSAGES = (
    _p('Proceed with installation?'),
    _p('Do you want to remove these packages?'),
)
DEFAULT_QUESTIONS = [
    bold_line(" {} {} ".format(message, _p('[Y/n]')))
    for message in QUESTION_MESSAGES
]
DEFAULT_ANSWER = _p("Y")


def handle_exception_in_thread(fun: Callable) -> Callable:

    def decorated(proc: subprocess.Popen, *args: Any, **kwargs: Any):
        try:
            return fun(proc, *args, **kwargs)
        # except OSError:
        # pass
        except Exception as exc:
            print('Error in the thread:')
            traceback.print_exc()
            raise exc

    return decorated


@handle_exception_in_thread
def output_handler(
        proc: subprocess.Popen,
        proc_output_reader: io.BytesIO,
        pty_in: io.TextIOWrapper,
        default_answer: str,
        default_questions: Tuple[str],
) -> None:
    historic_output = b''
    while True:
        if proc.returncode is not None:
            break
        output = proc_output_reader.read(1)
        if not output:
            break
        historic_output = historic_output[-50:] + output

        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
        for question in default_questions:
            if historic_output.rstrip().endswith(question.encode('utf-8')):
                sys.stdout.write(default_answer + '\n')
                sys.stdout.flush()
                pty_in.write(default_answer + '\n')
                historic_output = b''
                break
    print('output handler exiting')


@handle_exception_in_thread
def input_reader(
        proc: subprocess.Popen,
        pty_in: io.TextIOWrapper,
        lock: Lock
) -> None:
    while True:
        if proc.returncode is not None:
            break
        char = None

        while sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            line = sys.stdin.read(1)
            if line:
                char = line
                break
            else:
                return
        else:
            sleep(0.1)
            continue

        lock.acquire()
        try:
            pty_in.write(char)
        except ValueError:
            return
        sys.stdout.write(char)
        sys.stdout.flush()
        lock.release()


@handle_exception_in_thread
def communicator(proc: subprocess.Popen) -> None:
    proc.communicate()
    if sys.stdin.isatty():
        termios.tcflush(sys.stdin.fileno(), termios.TCIOFLUSH)
    if sys.stderr.isatty():
        termios.tcdrain(sys.stderr.fileno())
    if sys.stdout.isatty():
        termios.tcdrain(sys.stdout.fileno())


def pikspect(
        cmd: List[str],
        default_answer=DEFAULT_ANSWER,
        default_questions=DEFAULT_QUESTIONS,
        **kwargs
) -> subprocess.Popen:
    if sys.stdin.isatty():
        old_tcattrs = termios.tcgetattr(sys.stdin.fileno())
        tty.setcbreak(sys.stdin.fileno())
    if sys.stderr.isatty():
        tty.setcbreak(sys.stderr.fileno())
    if sys.stdout.isatty():
        tty.setcbreak(sys.stdout.fileno())

    pty_master, pty_slave = pty.openpty()
    pty_master2, pty_slave2 = pty.openpty()
    with ThreadPool() as pool:
        with open(pty_master, 'w') as pty_in:

            pty_out = open(pty_master2, 'rb')

            if 'sudo' in cmd:
                subprocess.run(isolate_root_cmd(['sudo', '-v']))
            proc = subprocess.Popen(
                cmd,
                stdin=pty_slave,
                stdout=pty_slave2,
                # stderr=pty_slave2,
                stderr=subprocess.STDOUT,
                **kwargs)
            pool.apply_async(output_handler, (
                proc,
                pty_out,
                pty_in,
                default_answer,
                default_questions,
            ))
            pool.apply_async(input_reader, (
                proc,
                pty_in,
                Lock(),
            ))
            communicate_task = pool.apply_async(communicator, (proc, ))

            pool.close()
            communicate_task.get()
            pool.terminate()
    if sys.stdin.isatty():
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, old_tcattrs)
    return proc


if __name__ == "__main__":
    pikspect(
        [
            'sudo',
            'pacman',
        ] + sys.argv[1:],
    )
