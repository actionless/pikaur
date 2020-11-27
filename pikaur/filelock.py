import fcntl

from .i18n import _
from .exceptions import SysExit
from .pprint import print_error
from .prompt import ask_to_continue


class FileLock():

    def __init__(self, lock_file_path: str) -> None:
        self.lock_file_path = lock_file_path
        self.lock_file = open(lock_file_path, 'a')

    def __enter__(self) -> None:
        while True:
            try:
                fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as err:
                print_error(_("Can't lock {lock_file}: {reason}").format(
                    lock_file=self.lock_file_path,
                    reason=err.strerror
                ))
                if not ask_to_continue(_('Do you want to retry?')):
                    raise SysExit(128) from err

    def __exit__(self, *_exc_details) -> None:
        fcntl.flock(self.lock_file, fcntl.LOCK_UN)
        self.lock_file.close()
