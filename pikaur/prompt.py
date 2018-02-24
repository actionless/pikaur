import sys
import tty

from .core import interactive_spawn
from .pprint import color_line


def get_answer(question, answers='Yn'):
    '''
    Function displays a question and reads a single character
    from STDIN as an answer. Then returns the character as lower character.
    Valid answers are passed as 'answers' variable (the default is in capital).
    Invalid answer will return default value.
    '''

    default = ''

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
        if answer in answers:
            return answer
        else:
            return default
    except Exception() as err:
        return default
    finally:
        tty.tcsetattr(sys.stdin.fileno(), tty.TCSADRAIN, previous_tty_settings)
        sys.stdout.write('{}\r\n'.format(answer))
        tty.tcdrain(sys.stdin.fileno())


def ask_to_continue(text='Do you want to proceed?', default_yes=True):
    if default_yes:
        answer = get_answer('{} [Y/n] ', answers='Yn')
        if answer and answer != 'y':
            return False
    else:
        answer = get_answer('{} [y/N] ', answers='yN')
        if not answer or answer != 'y':
            return False
    return True


def ask_to_retry_decorator(fun):

    def decorated(*args, **kwargs):
        while True:
            result = fun(*args, **kwargs)
            if result:
                return result
            if not ask_to_continue('Do you want to retry?'):
                return None

    return decorated


@ask_to_retry_decorator
def retry_interactive_command(cmd_args, **kwargs):
    good = interactive_spawn(cmd_args, **kwargs).returncode == 0
    if not good:
        print(color_line('Command "{}" failed to execute.'.format(
            ' '.join(cmd_args)
        ), 9))
    return good


def retry_interactive_command_or_exit(cmd_args, **kwargs):
    if not retry_interactive_command(cmd_args, **kwargs):
        if not ask_to_continue(default_yes=False):
            sys.exit(1)
