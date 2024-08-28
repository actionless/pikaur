"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import math
import shutil
import sys
import termios
from itertools import zip_longest
from typing import TYPE_CHECKING

from .args import ColorFlagValues, parse_args
from .config import DECORATION
from .i18n import translate
from .lock import FancyLock

if TYPE_CHECKING:
    from typing import Any, Final, TextIO

TcAttrsType = list[int | list[bytes | int]]


PADDING: "Final" = 4

ESCAPE: "Final" = "\033"
BOLD_START: "Final" = f"{ESCAPE}[0;1m"
BOLD_RESET: "Final" = f"{ESCAPE}[0m"
COLOR_RESET: "Final" = f"{ESCAPE}[0;0m"

NON_PRINTABLE: "Final" = {ESCAPE}


class TTYRestore:

    old_tcattrs = None
    old_tcattrs_out = None
    old_tcattrs_err = None

    @classmethod
    def save(cls) -> None:
        if sys.stdin.isatty():
            cls.old_tcattrs = termios.tcgetattr(sys.stdin.fileno())
        if sys.stdout.isatty():
            cls.old_tcattrs_out = termios.tcgetattr(sys.stdout.fileno())
        if sys.stderr.isatty():
            cls.old_tcattrs_err = termios.tcgetattr(sys.stderr.fileno())

    @classmethod
    def _restore(
            cls,
            what: TcAttrsType | None = None,
            what_out: TcAttrsType | None = None,
            what_err: TcAttrsType | None = None,
    ) -> None:
        if what:
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, what)
            except termios.error as exc:
                print_error(",".join(str(arg) for arg in exc.args), lock=False)
        if what_out:
            try:
                termios.tcsetattr(sys.stdout.fileno(), termios.TCSANOW, what_out)
            except termios.error as exc:
                print_error(",".join(str(arg) for arg in exc.args), lock=False)
        if what_err:
            try:
                termios.tcsetattr(sys.stderr.fileno(), termios.TCSANOW, what_err)
            except termios.error as exc:
                print_error(",".join(str(arg) for arg in exc.args), lock=False)

    @classmethod
    def restore(cls, *_whatever: "Any") -> None:
        cls._restore(cls.old_tcattrs, cls.old_tcattrs_out, cls.old_tcattrs_err)


class TTYRestoreContext:

    def __init__(self, *, before: bool = False, after: bool = True) -> None:
        self.before = before
        self.after = after

    def __enter__(self) -> None:
        if self.before:
            TTYRestore.restore()

    def __exit__(self, *exc_details: object) -> None:
        if self.after:
            TTYRestore.restore()


def color_enabled() -> bool:
    args = parse_args()
    if args.color == ColorFlagValues.NEVER:
        return False
    if args.color == ColorFlagValues.ALWAYS:
        return True
    try:
        if (sys.stderr.isatty() and sys.stdout.isatty()):
            return True
    except Exception:
        return False
    return False


class PrintLock(FancyLock):
    pass


def _print(
        destination: "TextIO",
        message: "Any" = "",
        end: str = "\n",
        *,
        flush: bool = False,
        lock: bool = True,
        tty_restore: bool = False,
) -> None:
    # pylint: disable=unnecessary-dunder-call
    if not isinstance(message, str):
        message = str(message)
    if lock:
        PrintLock().__enter__()  # noqa: PLC2801
    if tty_restore:
        TTYRestore.restore()
    destination.write(f"{message}{end}")
    if flush:
        destination.flush()
    if lock:
        PrintLock().__exit__()


def print_stdout(
        message: "Any" = "",
        end: str = "\n",
        *,
        flush: bool = False,
        lock: bool = True,
        tty_restore: bool = False,
) -> None:
    _print(sys.stdout, message=message, end=end, flush=flush, lock=lock, tty_restore=tty_restore)


def print_stderr(
        message: "Any" = "",
        end: str = "\n",
        *,
        flush: bool = False,
        lock: bool = True,
        tty_restore: bool = False,
) -> None:
    _print(sys.stderr, message=message, end=end, flush=flush, lock=lock, tty_restore=tty_restore)


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


def color_start(
        color_number: int,
) -> str:
    result = ""
    if color_number >= ColorsHighlight.black:
        result += BOLD_START
        color_number -= ColorsHighlight.black
    result += f"{ESCAPE}[03{color_number}m"
    return result


def color_line(
        line: str, color_number: int, *, reset: bool = True, force: bool = False,
) -> str:
    if not color_enabled() and not force:
        return line
    result = f"{color_start(color_number)}{line}"
    # reset font:
    if reset:
        result += COLOR_RESET
    return result


def bold_line(line: str) -> str:
    if not color_enabled():
        return line
    return f"{BOLD_START}{line}{BOLD_RESET}"


def print_warning(
        message: str = "",
        *,
        flush: bool = False,
        lock: bool = True,
        tty_restore: bool = False,
) -> None:
    print_stderr(
        " ".join([
            color_line(" ".join((DECORATION, translate("warning:"))), ColorsHighlight.yellow),
            message,
        ]),
        lock=lock,
        flush=flush,
        tty_restore=tty_restore,
    )


def print_error(
        message: str = "",
        *,
        flush: bool = False,
        lock: bool = True,
        tty_restore: bool = False,
) -> None:
    print_stderr(
        " ".join([
            color_line(" ".join((DECORATION, translate("error:"))), ColorsHighlight.red),
            message,
        ]),
        lock=lock,
        flush=flush,
        tty_restore=tty_restore,
    )


def get_term_width() -> int:
    return shutil.get_terminal_size((80, 80)).columns


def printable_length(text: str) -> int:
    counter = 0
    escape_seq = False
    for char in text:
        if not escape_seq and (char not in NON_PRINTABLE):
            counter += 1
        elif escape_seq and char == "m":
            escape_seq = False
        else:
            escape_seq = True
    return counter


def range_printable(text: str, start: int = 0, end: int | None = None) -> str:
    if not end:
        end = len(text)

    result = ""
    counter = 0
    escape_seq = False
    for char in text:
        if counter >= start:
            result += char
        if not escape_seq and (char not in NON_PRINTABLE):
            counter += 1
        elif escape_seq and char == "m":
            escape_seq = False
        else:
            escape_seq = True
        if counter >= end:
            break
    return result


def format_paragraph(
        text: str, padding: int = PADDING, width: int | None = None,
        *,
        force: bool = False, split_words: bool = False,
) -> str:
    if not (force or color_enabled()):
        return padding * " " + text
    term_width = width or get_term_width()
    max_line_width = term_width - padding * 2

    result = []
    current_line: list[str] = []
    line_length = 0

    def create_linebreak() -> None:
        nonlocal result, current_line, line_length
        while current_line and (current_line[-1] in {" ", "\t"}):
            del current_line[-1]
        result.append(current_line)
        current_line = []
        line_length = 0

    for line in text.splitlines():
        if not line:
            create_linebreak()
            continue
        for word_raw in line.split(" "):
            if split_words:
                words = [
                    range_printable(word_raw, i * max_line_width, (i + 1) * max_line_width)
                    for i in range(math.ceil(printable_length(word_raw) / max_line_width))
                ]
            else:
                words = [word_raw]
            if not words:
                if line_length + 1 > max_line_width:
                    create_linebreak()
                current_line.append(" ")
                line_length += 1
            for word in words:
                if printable_length(word) + line_length > max_line_width:
                    create_linebreak()
                current_line.extend((word, " "))
                line_length += printable_length(word) + 1
        if current_line:
            create_linebreak()
    if current_line:
        result.append(current_line)

    return "\n".join([
        "".join([
            padding * " ", *words, padding * " ",
        ])
        for words in result
    ])


def make_equal_right_padding(multiline_string: str, length: int | None = None) -> str:
    lines = multiline_string.splitlines()
    max_string_length = max(printable_length(line) for line in lines)
    if length:
        if length < max_string_length:
            message = f"{length=} < {max_string_length=}"
            raise ValueError(message)
        target_length = length
    else:
        target_length = max_string_length
    return "\n".join(
        "".join((line, *([" "] * (target_length - printable_length(line)))))
        for line in lines
    )


def sidejoin_multiline_paragraphs(join_separator: str, *multiline_strings: str) -> str:
    return "\n".join(
        join_separator.join(line or "" for line in lines)
        for lines in zip_longest(
            *(multiline_string.splitlines() for multiline_string in multiline_strings),
        )
    )
