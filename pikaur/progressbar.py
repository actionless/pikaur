""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import sys
from threading import Lock
from typing import Callable, Dict

from .pprint import get_term_width, color_enabled


class ProgressBar():

    print_ratio: float
    index = 0
    progress = 0

    LEFT_DECORATION = '['
    RIGHT_DECORATION = ']'
    EMPTY = '-'
    FULL = '#'

    def __init__(self, length: int, message='') -> None:
        width = (
            get_term_width() - len(message) - len(self.LEFT_DECORATION) - len(self.RIGHT_DECORATION)
        )
        self.print_ratio = length / width
        sys.stderr.write(message)
        if color_enabled():
            sys.stderr.write(self.LEFT_DECORATION + self.EMPTY * width + self.RIGHT_DECORATION)
            sys.stderr.write(f'{(chr(27))}[\bb' * (width + len(self.RIGHT_DECORATION)))

    def update(self) -> None:
        self.index += 1
        if self.index / self.print_ratio > self.progress:
            self.progress += 1
            if color_enabled():
                sys.stderr.write(self.FULL)

    def __enter__(self) -> Callable:
        return self.update

    def __exit__(self, *_exc_details) -> None:
        sys.stderr.write('\n')


class ThreadSafeProgressBar():

    _progressbar_storage: Dict[str, ProgressBar] = {}
    _progressbar_lock = Lock()

    @classmethod
    def get(cls, progressbar_length: int, progressbar_id: str) -> ProgressBar:
        if progressbar_id not in cls._progressbar_storage:
            cls._progressbar_lock.acquire()
            if progressbar_id not in cls._progressbar_storage:
                sys.stderr.write('\n')
                cls._progressbar_storage[progressbar_id] = ProgressBar(
                    length=progressbar_length,
                    message="Synchronizing AUR database... "
                )
            cls._progressbar_lock.release()
        return cls._progressbar_storage[progressbar_id]
