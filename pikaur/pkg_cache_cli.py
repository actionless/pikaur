import os
from typing import Callable, TYPE_CHECKING

from .args import parse_args, reconstruct_args
from .config import (
    BUILD_CACHE_PATH,
    PACKAGE_CACHE_PATH,
    PikaurConfig,
)
from .core import (
    interactive_spawn,
    remove_dir,
    sudo,
)
from .exceptions import SysExit
from .i18n import translate
from .pikspect import (
    pikspect,
)
from .pprint import (
    ColorsHighlight,
    bold_line,
    color_line,
    create_debug_logger,
    print_stdout,
)
from .prompt import ask_to_continue

if TYPE_CHECKING:
    from subprocess import Popen  # nosec B404


_debug = create_debug_logger('pkg_cache_cli')


def cli_clean_packages_cache() -> None:
    args = parse_args()
    if not args.repo:
        for directory, message, minimal_clean_level in (
                (BUILD_CACHE_PATH, translate("Build directory"), 1, ),
                (PACKAGE_CACHE_PATH, translate("Packages directory"), 2, ),
        ):
            if minimal_clean_level <= args.clean and os.path.exists(directory):
                print_stdout(f"\n{message}: {directory}")
                if ask_to_continue(text='{} {}'.format(  # pylint: disable=consider-using-f-string
                        color_line('::', ColorsHighlight.blue),
                        bold_line(translate("Do you want to remove all files?"))
                )):
                    remove_dir(directory)
    if not args.aur:
        spawn_func: Callable[[list[str]], 'Popen'] = interactive_spawn
        if args.noconfirm:
            spawn_func = pikspect
        raise SysExit(
            spawn_func(sudo(
                [PikaurConfig().misc.PacmanPath.get_str(), ] +
                reconstruct_args(args, ignore_args=['noconfirm', ])
            )).returncode
        )
