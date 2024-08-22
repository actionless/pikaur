import fcntl
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .config import DEFAULT_INPUT_ENCODING
from .logging_extras import create_logger

if TYPE_CHECKING:
    from typing import Final, TextIO


logger_no_lock = create_logger("FileLock", lock=False)


LOCK_CHECK_INTERVAL: "Final" = 0.01  # seconds


class FileLock:

    locked = False
    lock_file: "TextIO | None"

    def __init__(self, lock_file_path: str | Path) -> None:
        self.lock_file_path = Path(lock_file_path)

    def __enter__(self) -> None:
        logger_no_lock.debug(
            "Acquiring {lock_file}...",
            lock_file=self.lock_file_path,
        )
        self.lock_file = self.lock_file_path.open("a", encoding=DEFAULT_INPUT_ENCODING)
        already_logged = False
        while True:
            try:
                fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.locked = True
                break
            except BlockingIOError as err:
                if not already_logged:
                    logger_no_lock.debug(
                        "Can't lock {lock_file}: {reason}",
                        lock_file=self.lock_file_path,
                        reason=err.strerror,
                    )
                    already_logged = True
                time.sleep(LOCK_CHECK_INTERVAL)
        logger_no_lock.debug(
            "Acquired {lock_file}",
            lock_file=self.lock_file_path,
        )

    def __exit__(self, *_exc_details: object) -> None:
        if self.lock_file:
            logger_no_lock.debug(
                "Releasing {lock_file}",
                lock_file=self.lock_file_path,
            )
            if self.locked:
                fcntl.flock(self.lock_file, fcntl.LOCK_UN)
            if not self.lock_file.closed:
                self.lock_file.close()
            self.lock_file = None
            self.locked = False
            if self.lock_file_path.exists():
                self.lock_file_path.unlink()
                logger_no_lock.debug(
                    "Released {lock_file}",
                    lock_file=self.lock_file_path,
                )

    def __del__(self) -> None:
        self.__exit__()
