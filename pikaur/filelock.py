import fcntl
from pathlib import Path
from typing import TYPE_CHECKING

from .core import DEFAULT_INPUT_ENCODING
from .exceptions import SysExit
from .i18n import translate
from .pprint import print_error
from .prompt import ask_to_continue

if TYPE_CHECKING:
    from typing import Any, TextIO


class FileLock():

    locked = False
    lock_file: "TextIO | None"

    def __init__(self, lock_file_path: str | Path) -> None:
        self.lock_file_path = Path(lock_file_path)

    def __enter__(self) -> None:
        self.lock_file = self.lock_file_path.open("a", encoding=DEFAULT_INPUT_ENCODING)
        while True:
            try:
                fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.locked = True
                break
            except BlockingIOError as err:
                print_error(translate("Can't lock {lock_file}: {reason}").format(
                    lock_file=self.lock_file_path,
                    reason=err.strerror,
                ))
                if not ask_to_continue(translate("Do you want to retry?")):
                    raise SysExit(128) from err

    def __exit__(self, *_exc_details: "Any") -> None:
        if self.lock_file:
            if self.locked:
                fcntl.flock(self.lock_file, fcntl.LOCK_UN)
            if not self.lock_file.closed:
                self.lock_file.close()
        self.locked = False
        if self.lock_file_path.exists():
            self.lock_file_path.unlink()

    def __del__(self) -> None:
        self.__exit__()
