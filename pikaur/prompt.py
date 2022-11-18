"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import sys
import tty
from typing import Iterable, Sequence

from .args import parse_args
from .config import PikaurConfig
from .core import get_editor, interactive_spawn
from .exceptions import SysExit
from .i18n import translate
from .pikspect import TTYInputWrapper, TTYRestore
from .pikspect import pikspect as pikspect_spawn
from .pprint import (
    ColorsHighlight,
    PrintLock,
    color_line,
    create_debug_logger,
    get_term_width,
    print_stderr,
    print_warning,
    range_printable,
)


Y = translate('y')
N = translate('n')

Y_UP = Y.upper()
N_UP = N.upper()

_debug = create_debug_logger('prompt')
_debug_nolock = create_debug_logger('prompt_nolock', lock=False)


def read_answer_from_tty(question: str, answers: Sequence[str] = (Y_UP, N, )) -> str:
    """
    Function displays a question and reads a single character
    from STDIN as an answer. Then returns the character as lower character.
    Valid answers are passed as 'answers' variable (the default is in capital).
    Invalid answer will return an empty string.
    """
    default = ' '

    for letter in answers:
        if letter.isupper():
            default = letter.lower()
            break

    if not sys.stdin.isatty():
        return default

    print_stderr(question, flush=True, end=" ", lock=False)
    previous_tty_settings = tty.tcgetattr(sys.stdin.fileno())  # type: ignore[attr-defined]
    try:
        tty.setraw(sys.stdin.fileno())
        answer = sys.stdin.read(1).lower()

        # Exit when CRTL+C or CTRL+D
        if ord(answer) == 3 or ord(answer) == 4:
            raise SysExit(1)
        # Default when Enter
        if ord(answer) == 13:
            answer = default
            return default
        if answer in [choice.lower() for choice in answers]:
            return answer
        return ' '
    except Exception:
        return ' '
    finally:
        tty.tcsetattr(  # type: ignore[attr-defined]
            sys.stdin.fileno(), tty.TCSADRAIN, previous_tty_settings  # type: ignore[attr-defined]
        )
        sys.stdout.write(f'{answer}\r\n')
        tty.tcdrain(sys.stdin.fileno())  # type: ignore[attr-defined]


def split_last_line(text: str) -> str:
    all_lines = text.split('\n')
    n_lines = len(all_lines)
    last_line = all_lines[n_lines - 1]
    term_width = get_term_width()
    if len(last_line) < term_width:
        return text
    prev_lines = all_lines[:n_lines - 1]
    last_line = "{}\n{}".format(  # pylint: disable=consider-using-f-string
        range_printable(last_line, 0, term_width),
        range_printable(last_line, term_width)
    )
    return '\n'.join(prev_lines + [last_line])


def get_input(
        prompt: str, answers: Sequence[str] = (), require_confirm: bool = False
) -> str:
    _debug('Gonna get input from user...')
    answer = ''
    with PrintLock():
        with TTYInputWrapper():

            if not (
                    require_confirm or PikaurConfig().ui.RequireEnterConfirm.get_bool()
            ):
                _debug_nolock('Using custom input reader...')
                answer = read_answer_from_tty(prompt, answers=answers)
            else:
                _debug_nolock('Restoring TTY...')
                sub_tty = TTYRestore()
                TTYRestore.restore()
                try:
                    _debug_nolock('Using standard input reader...')
                    answer = input(split_last_line(prompt)).lower()
                except EOFError as exc:
                    _debug_nolock(exc)
                    raise SysExit(125) from exc
                finally:
                    _debug_nolock('Reverting to prev TTY state...')
                    sub_tty.restore_new()

    if not answer:
        for choice in answers:
            if choice.isupper():
                _debug(f'No answer provided - using "{choice}".')
                return choice.lower()
    _debug(f"Got answer: '{answer}'")
    return answer


class NotANumberInputError(Exception):
    character: str

    def __init__(self, character: str):
        self.character = character
        super().__init__(f'"{character} is not a number')


def get_multiple_numbers_input(prompt: str, answers: Iterable[int] = ()) -> list[int]:
    str_result = get_input(prompt, [str(answer) for answer in answers], require_confirm=True)
    if str_result == '':
        return []
    str_results = str_result.replace(',', ' ').split(' ')
    int_results: list[int] = []
    for block in str_results[:]:
        if '..' in block:
            block = block.replace('..', '-')
        if '-' in block:
            try:
                range_start, range_end = [int(char) for char in block.split('-')]
            except ValueError as exc:
                raise NotANumberInputError(block) from exc
            if range_start > range_end:
                raise NotANumberInputError(block)
            int_results += list(range(range_start, range_end + 1))
        else:
            try:
                int_results.append(int(block))
            except ValueError as exc:
                raise NotANumberInputError(exc.args[0].split("'")[-2]) from exc
    return int_results


def ask_to_continue(text: str | None = None, default_yes: bool = True) -> bool:
    args = parse_args()
    if text is None:
        text = translate('Do you want to proceed?')

    if args.noconfirm:
        default_option = ("[Y]es (--noconfirm)") if default_yes else translate("[N]o (--noconfirm)")
        print_stderr(f'{text} {default_option}')
        return default_yes

    prompt = text + (f' [{Y_UP}/{N}] ' if default_yes else f' [{Y}/{N_UP}] ')
    answers = Y_UP + N if default_yes else Y + N_UP

    answer = get_input(prompt, answers)
    return (answer == Y) or (default_yes and answer == '')


def retry_interactive_command(
        cmd_args: list[str],
        pikspect: bool = False,
        conflicts: list[list[str]] | None = None,
) -> bool:
    args = parse_args()
    while True:
        good = None
        if pikspect and ('--noconfirm' not in cmd_args):
            good = pikspect_spawn(
                cmd_args,
                conflicts=conflicts,
            ).returncode == 0
        else:
            good = interactive_spawn(
                cmd_args
            ).returncode == 0
        if good:
            return good
        print_stderr(color_line(
            translate("Command '{}' failed to execute.").format(
                ' '.join(cmd_args)
            ),
            ColorsHighlight.red
        ))
        if not ask_to_continue(
                text=translate("Do you want to retry?"),
                default_yes=not args.noconfirm
        ):
            return False


def retry_interactive_command_or_exit(
        cmd_args: list[str],
        pikspect: bool = False,
        conflicts: list[list[str]] | None = None,
) -> None:
    if not retry_interactive_command(
            cmd_args,
            pikspect=pikspect,
            conflicts=conflicts,
    ):
        if not ask_to_continue(default_yes=False):
            raise SysExit(125)


def get_editor_or_exit() -> list[str] | None:
    editor = get_editor()
    if not editor:
        print_warning(translate("no editor found. Try setting $VISUAL or $EDITOR."))
        if not ask_to_continue(
                translate("Do you want to proceed without editing?")
        ):  # pragma: no cover
            raise SysExit(125)
    return editor
