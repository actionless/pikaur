""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import traceback
from typing import Callable, Any

from .pprint import print_stderr


def handle_exception_in_thread(fun: Callable) -> Callable:

    def decorated(*args: Any, **kwargs: Any):
        try:
            return fun(*args, **kwargs)
        # except OSError:
        # pass
        except Exception as exc:
            print_stderr('Error in the thread:')
            traceback.print_exc()
            raise exc

    return decorated
