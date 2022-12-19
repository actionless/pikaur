import os
from typing import TYPE_CHECKING, Callable

from .args import parse_args, reconstruct_args
from .config import BUILD_CACHE_PATH, PACKAGE_CACHE_PATH, PikaurConfig
from .core import interactive_spawn, remove_dir, sudo
from .exceptions import SysExit
from .i18n import translate
from .pikspect import YesNo, format_pacman_question, pikspect
from .pprint import ColorsHighlight, bold_line, color_line, create_debug_logger, print_stdout
from .prompt import ask_to_continue

if TYPE_CHECKING:
    from subprocess import Popen  # nosec B404


_debug = create_debug_logger("pkg_cache_cli")


def clean_aur_cache() -> None:
    args = parse_args()
    for directory, message, minimal_clean_level in (
            (BUILD_CACHE_PATH, translate("Build directory"), 1, ),
            (PACKAGE_CACHE_PATH, translate("Packages directory"), 2, ),
    ):
        print_stdout(f"\n{message}: {directory}")
        if minimal_clean_level <= args.clean and os.path.exists(directory):
            if ask_to_continue(text="{} {}".format(  # pylint: disable=consider-using-f-string
                    color_line("::", ColorsHighlight.blue),
                    bold_line(translate("Do you want to remove all files?"))
            )):
                print_stdout(translate("removing all files from cache..."))
                remove_dir(directory)
        else:
            print_stdout(translate("Directory is empty."))


def clean_repo_cache() -> None:
    args = parse_args()
    spawn_func: Callable[[list[str]], "Popen[bytes]"] = interactive_spawn
    if args.noconfirm:

        def noconfirm_cache_remove(pacman_args: list[str]) -> "Popen[bytes]":
            return pikspect(pacman_args, extra_questions={YesNo.ANSWER_Y: [
                format_pacman_question(
                    "Do you want to remove ALL files from cache?",
                    question=YesNo.QUESTION_YN_NO,
                ),
                format_pacman_question(
                    "Do you want to remove all other packages from cache?"
                ),
                format_pacman_question(
                    "Do you want to remove unused repositories?",
                ),
            ]})
        spawn_func = noconfirm_cache_remove
    raise SysExit(
        spawn_func(sudo(
            [PikaurConfig().misc.PacmanPath.get_str(), ] +
            reconstruct_args(args, ignore_args=["noconfirm", ])
        )).returncode
    )


def cli_clean_packages_cache() -> None:
    args = parse_args()
    if not args.repo:
        clean_aur_cache()
    if not args.aur:
        clean_repo_cache()
