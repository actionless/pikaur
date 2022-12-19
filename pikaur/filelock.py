import fcntl
import os
from typing import Any, TextIO

from .core import DEFAULT_INPUT_ENCODING
from .exceptions import SysExit
from .i18n import translate
from .pprint import print_error
from .prompt import ask_to_continue


class FileLock():

    locked = False
    lock_file: TextIO | None

    def __init__(self, lock_file_path: str) -> None:
        self.lock_file_path = lock_file_path

    def __enter__(self) -> None:
        self.lock_file = open(
            self.lock_file_path, "a", encoding=DEFAULT_INPUT_ENCODING
        )
        while True:
            try:
                fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.locked = True
                break
            except BlockingIOError as err:
                print_error(translate("Can't lock {lock_file}: {reason}").format(
                    lock_file=self.lock_file_path,
                    reason=err.strerror
                ))
                if not ask_to_continue(translate("Do you want to retry?")):
                    raise SysExit(128) from err

    def __exit__(self, *_exc_details: Any) -> None:
        if self.lock_file:
            if self.locked:
                fcntl.flock(self.lock_file, fcntl.LOCK_UN)
            if not self.lock_file.closed:
                self.lock_file.close()
        self.locked = False
        if os.path.exists(self.lock_file_path):
            os.remove(self.lock_file_path)

    def __del__(self) -> None:
        self.__exit__()
