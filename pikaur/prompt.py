import sys
import tty
from typing import Callable, List

from .args import PikaurArgs
from .config import PikaurConfig

from .core import interactive_spawn
from .i18n import _
from .pprint import color_line, print_status_message


def get_answer(question: str, answers: str='Yn') -> str:
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

    print(question, flush=True, end=" ")
    previous_tty_settings = tty.tcgetattr(sys.stdin.fileno())
    try:
        tty.setraw(sys.stdin.fileno())
        answer = sys.stdin.read(1).lower()

        # Exit when CRTL+C or CTRL+D
        if ord(answer) == 3 or ord(answer) == 4:
            sys.exit(1)
        # Default when Enter
        if ord(answer) == 13:
            answer = default
            return default
        if answer in answers:
            return answer
        return ' '
    except Exception:
        return ' '
    finally:
        tty.tcsetattr(sys.stdin.fileno(), tty.TCSADRAIN, previous_tty_settings)
        sys.stdout.write('{}\r\n'.format(answer))
        tty.tcdrain(sys.stdin.fileno())


def get_input(prompt: str, answers: str=None) -> str:
    if PikaurConfig().ui.get('RequireEnterConfirm'):
        answer = input(prompt).lower()
    else:
        answer = get_answer(prompt, answers=answers)

    return answer


def ask_to_continue(text: str, default_yes: bool=True, args: PikaurArgs=None) -> bool:
    if text is None:
        text = 'Do you want to proceed?'

    if args and args.noconfirm and default_yes:
        print_status_message('{} {}'.format(text, _("[Y]es (--noconfirm)")))

    prompt = text + (' [Y/n] ' if default_yes else ' [y/N] ')
    answers = 'Yn' if default_yes else 'yN'

    answer = get_input(prompt, answers)
    return answer == 'y'


def ask_to_retry_decorator(fun: Callable) -> Callable:

    def decorated(*args, **kwargs):
        while True:
            result = fun(*args, **kwargs)
            if result:
                return result
            if not ask_to_continue(_("Do you want to retry?")):
                return None

    return decorated


@ask_to_retry_decorator
def retry_interactive_command(cmd_args: List[str], **kwargs) -> bool:
    good = interactive_spawn(cmd_args, **kwargs).returncode == 0
    if not good:
        print_status_message(color_line(_("Command '{}' failed to execute.").format(
            ' '.join(cmd_args)
        ), 9))
    return good


def retry_interactive_command_or_exit(cmd_args: List[str], **kwargs) -> None:
    if not retry_interactive_command(cmd_args, **kwargs):
        if not ask_to_continue(default_yes=False):
            sys.exit(125)
