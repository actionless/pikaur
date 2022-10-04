""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import sys
import shutil
from threading import Lock
from string import printable
import typing as t
from typing import List, Optional, TextIO, Any

from .i18n import translate
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
        if PRINT_LOCK.locked():
            PRINT_LOCK.release()

    def __del__(self):
        self.__exit__()


def _print(destination: TextIO, message='', end='\n', flush=False, lock=True) -> None:
    # pylint: disable=unnecessary-dunder-call
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


class Colors:
    black = 0
    red = 1
    green = 2
    yellow = 3
    blue = 4
    purple = 5
    cyan = 6
    white = 7


class ColorsHighlight:
    black = 8
    red = 9
    green = 10
    yellow = 11
    blue = 12
    purple = 13
    cyan = 14
    white = 15


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
        color_line(':: ' + translate("warning:"), ColorsHighlight.yellow),
        message
    ]))


def print_error(message: str) -> None:
    print_stderr(' '.join([
        color_line(':: ' + translate("error:"), ColorsHighlight.red),
        message
    ]))


def print_debug(message: Any, lock=True) -> None:
    if not ARGS.pikaur_debug:
        return
    prefix = translate("debug:")
    if ARGS.debug:
        # to avoid mixing together with pacman's debug messages:
        prefix = translate("pikaur debug:")
    print_stderr(' '.join([
        color_line(':: ' + prefix, Colors.cyan),
        str(message)
    ]), lock=lock)


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


class DebugColorCounter:

    # cyan is purposely skipped as it's used in print_debug itself,
    # highlight-red is purposely skipped as it's used in print_error,
    # highlight-yellow is purposely skipped as it's used in print_warning:
    colors = [
        Colors.red,
        Colors.green,
        Colors.yellow,
        Colors.blue,
        Colors.purple,
        Colors.white,
        ColorsHighlight.green,
        ColorsHighlight.blue,
        ColorsHighlight.purple,
        ColorsHighlight.cyan,
        ColorsHighlight.white,
    ]
    _current_color_idx = 0

    @classmethod
    def next(cls) -> int:
        color = cls.colors[cls._current_color_idx]
        cls._current_color_idx += 1
        if cls._current_color_idx >= len(cls.colors):
            cls._current_color_idx = 0
        return color


def create_debug_logger(module_name: str, **kwargs) -> t.Callable[..., None]:
    color = DebugColorCounter.next()

    def debug(msg: Any, *args2, **kwargs2) -> None:
        kwargs2.update(kwargs)
        print_debug(
            f"{color_line(module_name, color)}: {str(msg)}",
            *args2, **kwargs2
        )
    return debug
