from .args import parse_args, reconstruct_args
from .config import BUILD_CACHE_PATH, PACKAGE_CACHE_PATH, PikaurConfig
from .core import interactive_spawn, remove_dir, sudo
from .exceptions import SysExit
from .i18n import translate
from .logging import create_logger
from .pikspect import YesNo, format_pacman_question, pikspect
from .pprint import ColorsHighlight, bold_line, color_line, print_stdout
from .prompt import ask_to_continue

_debug = create_logger("pkg_cache_cli").debug


def clean_aur_cache() -> None:
    args = parse_args()
    for directory, message, minimal_clean_level in (
            (BUILD_CACHE_PATH, translate("Build directory"), 1),
            (PACKAGE_CACHE_PATH, translate("Packages directory"), 2),
    ):
        print_stdout(f"\n{message}: {directory}")
        if minimal_clean_level > args.clean:
            continue
        if not directory.exists():
            print_stdout(translate("Directory is empty."))
        elif ask_to_continue(text="{} {}".format(  # pylint: disable=consider-using-f-string
                color_line("::", ColorsHighlight.blue),
                bold_line(translate("Do you want to remove all files?")),
        )):
            print_stdout(translate("removing all files from cache..."))
            remove_dir(directory)


def clean_repo_cache() -> None:
    args = parse_args()

    if args.noconfirm:
        returncode = pikspect(
            sudo([
                PikaurConfig().misc.PacmanPath.get_str(),
                *reconstruct_args(args, ignore_args=["noconfirm"]),
            ]),
            extra_questions={YesNo.ANSWER_Y: [
                format_pacman_question(
                    "Do you want to remove ALL files from cache?",
                    question=YesNo.QUESTION_YN_NO,
                ),
                format_pacman_question(
                    "Do you want to remove all other packages from cache?",
                ),
                format_pacman_question(
                    "Do you want to remove unused repositories?",
                ),
            ]},
        ).returncode
        if returncode is None:
            returncode = 255
    else:
        returncode = interactive_spawn(sudo([
            PikaurConfig().misc.PacmanPath.get_str(),
            *reconstruct_args(args, ignore_args=["noconfirm"]),
        ])).returncode
    raise SysExit(returncode)


def cli_clean_packages_cache() -> None:
    args = parse_args()
    if not args.repo:
        clean_aur_cache()
    if not args.aur:
        clean_repo_cache()
