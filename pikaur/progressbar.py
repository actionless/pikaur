import sys
from typing import Callable

from .pprint import get_term_width


class ProgressBar(object):

    message: str = None
    print_ratio: float = None
    index = 0
    progress = 0

    LEFT_DECORATION = '['
    RIGHT_DECORATION = ']'
    EMPTY = '-'
    FULL = '#'

    def __init__(self, length: int, message='') -> None:
        self.message = message
        width = (
            get_term_width() - len(message) -
            len(self.LEFT_DECORATION) - len(self.RIGHT_DECORATION)
        )
        self.print_ratio = length / width
        sys.stderr.write(message)
        sys.stderr.write(self.LEFT_DECORATION + self.EMPTY * width + self.RIGHT_DECORATION)
        sys.stderr.write(f'{(chr(27))}[\bb' * (width + len(self.RIGHT_DECORATION)))

    def update(self) -> None:
        self.index += 1
        if self.index / self.print_ratio > self.progress:
            self.progress += 1
            sys.stderr.write(self.FULL)

    def __enter__(self) -> Callable:
        return self.update

    def __exit__(self, *exc_details) -> None:
        sys.stderr.write('\n')
