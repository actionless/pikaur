""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import sys
import tty
from typing import List, Optional

from .args import parse_args
from .config import PikaurConfig

from .core import interactive_spawn, get_editor
from .i18n import _
from .pprint import (
    color_line, print_stderr, get_term_width, range_printable,
    PrintLock, print_warning,
)
from .exceptions import SysExit


Y = _('y')
N = _('n')

Y_UP = Y.upper()
N_UP = N.upper()


def read_answer_from_tty(question: str, answers: str = Y_UP + N) -> str:
    '''
    Function displays a question and reads a single character
    from STDIN as an answer. Then returns the character as lower character.
    Valid answers are passed as 'answers' variable (the default is in capital).
    Invalid answer will return an empty string.
    '''

    default = ' '

    for letter in answers:
        if letter.isupper():
            default = letter.lower()
            break

    if not sys.stdin.isatty():
        return default

    print_stderr(question, flush=True, end=" ", lock=False)
    previous_tty_settings = tty.tcgetattr(sys.stdin.fileno())  # type: ignore
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
        if answer in answers.lower():
            return answer
        return ' '
    except Exception:
        return ' '
    finally:
        tty.tcsetattr(sys.stdin.fileno(), tty.TCSADRAIN, previous_tty_settings)  # type: ignore
        sys.stdout.write('{}\r\n'.format(answer))
        tty.tcdrain(sys.stdin.fileno())  # type: ignore


def split_last_line(text: str) -> str:
    all_lines = text.split('\n')
    n_lines = len(all_lines)
    last_line = all_lines[n_lines - 1]
    term_width = get_term_width()
    if len(last_line) < term_width:
        return text
    prev_lines = all_lines[:n_lines - 1]
    last_line = "{}\n{}".format(
        range_printable(last_line, 0, term_width),
        range_printable(last_line, term_width)
    )
    return '\n'.join(prev_lines + [last_line])


def get_input(prompt: str, answers=None) -> str:
    with PrintLock():
        if PikaurConfig().ui.get_bool('RequireEnterConfirm'):
            from .pikspect import TTYRestore
            sub_tty = TTYRestore()
            TTYRestore.restore()
            try:
                answer = input(split_last_line(prompt)).lower()
            except EOFError:
                raise SysExit(125)
            finally:
                sub_tty.restore_new()
            if not answer:
                for choice in answers:
                    if choice not in answers.lower():
                        return choice.lower()
        else:
            answer = read_answer_from_tty(prompt, answers=answers)
        return answer


def ask_to_continue(text: str = None, default_yes: bool = True) -> bool:
    args = parse_args()
    if text is None:
        text = _('Do you want to proceed?')

    if args.noconfirm:
        print_stderr('{} {}'.format(
            text,
            _("[Y]es (--noconfirm)") if default_yes else _("[N]o (--noconfirm)")
        ))
        return default_yes

    prompt = text + (' [%s/%s] ' % (Y_UP, N) if default_yes else ' [%s/%s] ' % (Y, N_UP))
    answers = Y_UP + N if default_yes else Y + N_UP

    answer = get_input(prompt, answers)
    return (answer == Y) or (default_yes and answer == '')


def retry_interactive_command(
        cmd_args: List[str],
        pikspect=False,
        **kwargs
) -> bool:
    args = parse_args()
    while True:
        good = None
        if pikspect:
            from .pikspect import pikspect as pikspect_spawn
            good = pikspect_spawn(cmd_args, **kwargs).returncode == 0
        else:
            if 'conflicts' in kwargs:
                del kwargs['conflicts']
            good = interactive_spawn(cmd_args, **kwargs).returncode == 0
        if good:
            return good
        print_stderr(color_line(_("Command '{}' failed to execute.").format(
            ' '.join(cmd_args)
        ), 9))
        if not ask_to_continue(
                text=_("Do you want to retry?"),
                default_yes=not args.noconfirm
        ):
            return False


def retry_interactive_command_or_exit(cmd_args: List[str], **kwargs) -> None:
    if not retry_interactive_command(cmd_args, **kwargs):
        if not ask_to_continue(default_yes=False):
            raise SysExit(125)


def get_editor_or_exit() -> Optional[List[str]]:
    editor = get_editor()
    if not editor:
        print_warning(_("no editor found. Try setting $VISUAL or $EDITOR."))
        if not ask_to_continue(_("Do you want to proceed without editing?")):  # pragma: no cover
            raise SysExit(125)
    return editor
