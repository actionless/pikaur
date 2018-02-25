import sys

from .core import interactive_spawn
from .pprint import color_line


def ask_to_continue(text='Do you want to proceed?', default_yes=True, args=None):
    if args and args.noconfirm and default_yes:
        print(text + '[Y]es (--noconfirm)')
        return True
    answer = input(text + (' [Y/n] ' if default_yes else ' [y/N] '))
    if default_yes:
        if answer and answer.lower()[0] != 'y':
            return False
    else:
        if not answer or answer.lower()[0] != 'y':
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
