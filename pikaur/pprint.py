import sys
import shutil
from threading import Lock
from string import printable
from typing import List, TYPE_CHECKING, Optional


if TYPE_CHECKING:
    # pylint: disable=unused-import
    from .args import PikaurArgs  # noqa


PADDING = 4
PRINT_LOCK = Lock()


class PrintLock(object):

    def __enter__(self) -> None:
        PRINT_LOCK.acquire()

    def __exit__(self, *_exc_details) -> None:
        PRINT_LOCK.release()


def print_stdout(message='', end='\n', flush=False) -> None:
    with PrintLock():
        sys.stdout.write(f'{message}{end}')
        if flush:
            sys.stdout.flush()


def print_stderr(message='', end='\n', flush=False) -> None:
    with PrintLock():
        sys.stderr.write(f'{message}{end}')
        if flush:
            sys.stderr.flush()


def color_enabled(args: 'PikaurArgs' = None) -> bool:
    if not args:
        from .args import parse_args
        args = parse_args()
    if args.color == 'never':
        return False
    if args.color == 'always' or (sys.stderr.isatty() and sys.stdout.isatty()):
        return True
    return False


def color_line(line: str, color_number: int) -> str:
    if not color_enabled():
        return line
    result = ''
    if color_number >= 8:
        result += "\033[0;1m"
        color_number -= 8
    result += f"\033[03{color_number}m{line}"
    # reset font:
    result += "\033[0;0m"
    return result


def bold_line(line: str) -> str:
    if not color_enabled():
        return line
    return f'\033[0;1m{line}\033[0m'


def get_term_width() -> int:
    return shutil.get_terminal_size((80, 80)).columns


def go_line_up():
    print_stdout('\033[1A', end='')


def purge_line():
    print_stdout(
        '\r' + ' ' * (get_term_width()) + bold_line('') + '\r',
        flush=True, end='',
    )


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
