"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import math
import sys
from threading import Lock
from typing import TYPE_CHECKING, ClassVar

from .pikaprint import color_enabled, get_term_width

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Final


def get_chunks(total: int, num_workers: int) -> list[int]:
    base_amount = int(total / num_workers)
    remaining = total - base_amount * num_workers
    remaining_per_worker = math.ceil(remaining / num_workers)

    num_workers_to_add_remaning = leftover = 0
    if remaining_per_worker:
        num_workers_to_add_remaning = remaining // remaining_per_worker
        leftover = remaining % remaining_per_worker

    result = [base_amount] * num_workers
    for i in range(num_workers_to_add_remaning):
        result[i] += remaining_per_worker
    result[num_workers_to_add_remaning] += leftover
    return result


class ProgressBar:

    progress = 0
    progress_step = 0

    LEFT_DECORATION: "Final" = "["
    RIGHT_DECORATION: "Final" = "]"
    EMPTY: "Final" = "-"
    FULL: "Final" = "#"

    def __init__(self, length: int, message: str = "") -> None:
        width = (
            get_term_width() - len(message) - len(self.LEFT_DECORATION) - len(self.RIGHT_DECORATION)
        )
        sys.stderr.write(message)
        if width >= length:
            self.progress_chunks = get_chunks(total=width, num_workers=length)
        else:
            self.progress_chunks = get_chunks(total=length, num_workers=width)
        if color_enabled():
            sys.stderr.write(self.LEFT_DECORATION + self.EMPTY * width + self.RIGHT_DECORATION)
            sys.stderr.write(f"{(chr(27))}[1D" * (width + len(self.RIGHT_DECORATION)))

        self.width = width
        self.length = length

    def update(self) -> None:
        step = self.progress_chunks[self.progress]
        if self.width >= self.length:
            self.progress += 1
            if color_enabled():
                for _ in range(step):
                    sys.stderr.write(self.FULL)
        else:
            self.progress_step += 1
            if self.progress_step >= step:
                self.progress_step = 0
                self.progress += 1
                if color_enabled():
                    sys.stderr.write(self.FULL)

    def __enter__(self) -> "Callable[[], None]":
        return self.update

    def __exit__(self, *_exc_details: object) -> None:
        sys.stderr.write("\n")


class ThreadSafeProgressBar:

    _progressbar_storage: ClassVar[dict[str, ProgressBar]] = {}
    _progressbar_lock: "Lock | None" = None

    @classmethod
    def get(
            cls,
            progressbar_length: int, progressbar_id: str,
            message: str = "Synchronizing AUR database... ",
    ) -> ProgressBar:
        if cls._progressbar_lock is None:
            cls._progressbar_lock = Lock()
        if progressbar_id not in cls._progressbar_storage:
            with cls._progressbar_lock:  # pylint: disable=not-context-manager
                if progressbar_id not in cls._progressbar_storage:
                    sys.stderr.write("\n")
                    cls._progressbar_storage[progressbar_id] = ProgressBar(
                        length=progressbar_length,
                        message=message,
                    )
        return cls._progressbar_storage[progressbar_id]
