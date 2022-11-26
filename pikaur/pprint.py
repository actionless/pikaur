"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import shutil
import sys
import typing as t
from string import printable
from threading import Lock
from typing import Any, TextIO

from .args import parse_args
from .i18n import translate


PADDING = 4
PRINT_LOCK = Lock()
ARGS = parse_args()


def color_enabled() -> bool:
    args = ARGS
    if args.color == 'never':
        return False
    if args.color == 'always':
        return True
    try:
        if (sys.stderr.isatty() and sys.stdout.isatty()):
            return True
    except Exception:
        return False
    return False


class PrintLock():

    def __enter__(self) -> None:
        PRINT_LOCK.acquire()

    def __exit__(self, *_exc_details: Any) -> None:
        if PRINT_LOCK.locked():
            PRINT_LOCK.release()

    def __del__(self) -> None:
        self.__exit__()


def _print(
        destination: TextIO,
        message: Any = '',
        end: str = '\n',
        flush: bool = False,
        lock: bool = True
) -> None:
    # pylint: disable=unnecessary-dunder-call
    if not isinstance(message, str):
        message = str(message)
    if lock:
        PrintLock().__enter__()
    destination.write(f'{message}{end}')
    if flush:
        destination.flush()
    if lock:
        PrintLock().__exit__()


def print_stdout(
        message: Any = '',
        end: str = '\n',
        flush: bool = False,
        lock: bool = True
) -> None:
    _print(sys.stdout, message=message, end=end, flush=flush, lock=lock)


def print_stderr(
        message: Any = '',
        end: str = '\n',
        flush: bool = False,
        lock: bool = True
) -> None:
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


def color_line(
        line: str, color_number: int, reset: bool = True, force: bool = False
) -> str:
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


def print_debug(message: Any, lock: bool = True) -> None:
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
    current_line: list[str] = []
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


def range_printable(text: str, start: int = 0, end: int | None = None) -> str:
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
    def get_next(cls) -> int:
        color = cls.colors[cls._current_color_idx]
        cls._current_color_idx += 1
        if cls._current_color_idx >= len(cls.colors):
            cls._current_color_idx = 0
        return color


def create_debug_logger(module_name: str, lock: bool | None = None) -> t.Callable[..., None]:
    color = DebugColorCounter.get_next()
    parent_lock = lock

    def debug(msg: Any, lock: bool | None = None) -> None:
        lock = lock if (lock is not None) else parent_lock
        msg = f"{color_line(module_name, color)}: {str(msg)}"
        if lock is not None:
            print_debug(msg, lock=lock)
        else:
            print_debug(msg)
    return debug
