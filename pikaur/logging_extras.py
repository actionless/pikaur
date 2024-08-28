"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

from logging import Logger
from typing import TYPE_CHECKING

from .args import parse_args
from .config import DECORATION
from .i18n import translate
from .pikaprint import Colors, ColorsHighlight, color_line, print_stderr

if TYPE_CHECKING:
    from typing import Any, Final


# cyan is purposely skipped as it's used in print_debug itself,
# highlight-red is purposely skipped as it's used in print_error,
# highlight-yellow is purposely skipped as it's used in print_warning:
DEBUG_COLORS: "Final[list[int]]" = [
    Colors.red,
    Colors.green,
    Colors.yellow,
    Colors.blue,
    Colors.purple,
    Colors.white,
    ColorsHighlight.green,
    ColorsHighlight.blue,
    ColorsHighlight.purple,
    ColorsHighlight.cyan,
    ColorsHighlight.white,
]


class DebugColorCounter:

    _current_color_idx = 0

    @classmethod
    def get_next(cls) -> int:
        color = DEBUG_COLORS[cls._current_color_idx]
        cls._current_color_idx += 1
        if cls._current_color_idx >= len(DEBUG_COLORS):
            cls._current_color_idx = 0
        return color


def print_debug(message: "Any", *, lock: bool = True) -> None:
    args = parse_args()
    if not args.pikaur_debug:
        return
    prefix = translate("debug:")
    if args.debug:
        # to avoid mixing together with pacman's debug messages:
        prefix = translate("pikaur debug:")
    print_stderr(" ".join((
        color_line(f"{DECORATION} {prefix}", Colors.cyan),
        str(message),
    )), lock=lock)


class PikaurLogger(Logger):  # we inherit `Logger` class only for pylint warnings to catch up on it
    def __init__(  # pylint: disable=super-init-not-called
            self,
            module_name: str,
            color: int,
            *,
            lock: bool | None = None,
    ) -> None:
        self.module_name = module_name
        self.color = color
        self.parent_lock = lock

    def debug(
        self,
        msg: "Any",
        *args: "Any",
        lock: bool | None = None, indent: int = 0,
        **kwargs: "Any",
    ) -> None:
        lock = lock if (lock is not None) else self.parent_lock
        str_message = msg.format(*args, **kwargs) if isinstance(msg, str) else str(msg)
        msg = f"{color_line(self.module_name, self.color)}: {' ' * indent}{str_message}"
        if lock is not None:
            print_debug(msg, lock=lock)
        else:
            print_debug(msg)


def create_logger(
        module_name: str, *, lock: bool | None = None,
) -> PikaurLogger:
    return PikaurLogger(module_name=module_name, color=DebugColorCounter.get_next(), lock=lock)
