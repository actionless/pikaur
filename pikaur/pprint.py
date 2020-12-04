""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import sys
import shutil
from threading import Lock
from string import printable
from typing import List, Optional, TextIO, Any

from .i18n import _
from .args import parse_args


PADDING = 4
PRINT_LOCK = Lock()
ARGS = parse_args()


def color_enabled() -> bool:
    args = ARGS
    if args.color == 'never':
        return False
    if args.color == 'always' or (sys.stderr.isatty() and sys.stdout.isatty()):
        return True
    return False


class PrintLock():

    def __enter__(self) -> None:
        PRINT_LOCK.acquire()

    def __exit__(self, *_exc_details) -> None:
        PRINT_LOCK.release()


def _print(destination: TextIO, message='', end='\n', flush=False, lock=True) -> None:
    if lock:
        PrintLock().__enter__()
    destination.write(f'{message}{end}')
    if flush:
        destination.flush()
    if lock:
        PrintLock().__exit__()


def print_stdout(message='', end='\n', flush=False, lock=True) -> None:
    _print(sys.stdout, message=message, end=end, flush=flush, lock=lock)


def print_stderr(message='', end='\n', flush=False, lock=True) -> None:
    _print(sys.stderr, message=message, end=end, flush=flush, lock=lock)


def color_line(line: str, color_number: int, reset=True, force=False) -> str:
    if not color_enabled() and not force:
        return line
    result = ''
    if color_number >= 8:
        result += "\033[0;1m"
        color_number -= 8
    result += f"\033[03{color_number}m{line}"
    # reset font:
    if reset:
        result += "\033[0;0m"
    return result


def bold_line(line: str) -> str:
    if not color_enabled():
        return line
    return f'\033[0;1m{line}\033[0m'


def print_warning(message: str = '') -> None:
    print_stderr(' '.join([
        color_line(':: ' + _("warning:"), 11),
        message
    ]))


def print_error(message: str) -> None:
    print_stderr(' '.join([
        color_line(':: ' + _("error:"), 9),
        message
    ]))


def print_debug(message: Any) -> None:
    if not ARGS.pikaur_debug:
        return
    prefix = _("debug:")
    if ARGS.debug:
        # to avoid mixing together with pacman's debug messages:
        prefix = _("pikaur debug:")
    print_stderr(' '.join([
        color_line(':: ' + prefix, 6),
        str(message)
    ]))


def get_term_width() -> int:
    return shutil.get_terminal_size((80, 80)).columns


def format_paragraph(line: str) -> str:
    if not color_enabled():
        return PADDING * ' ' + line
    term_width = get_term_width()
    max_line_width = term_width - PADDING * 2

    result = []
    current_line: List[str] = []
    line_length = 0
    for word in line.split():
        if len(word) + line_length > max_line_width:
            result.append(current_line)
            current_line = []
            line_length = 0
        current_line.append(word)
        line_length += len(word) + 1
    result.append(current_line)

    return '\n'.join([
        ' '.join(
            [(PADDING - 1) * ' ', ] +
            words +
            [(PADDING - 1) * ' ', ],
        )
        for words in result
    ])


def range_printable(text: str, start: int = 0, end: Optional[int] = None) -> str:
    if not end:
        end = len(text)

    result = ''
    counter = 0
    escape_seq = False
    for char in text:
        if counter >= start:
            result += char
        if not escape_seq and char in printable:
            counter += 1
        elif escape_seq and char == 'm':
            escape_seq = False
        else:
            escape_seq = True
        if counter >= end:
            break
    return result
