from .args import parse_args, reconstruct_args
from .config import DECORATION, BuildCachePath, PackageCachePath, PikaurConfig
from .exceptions import SysExit
from .i18n import translate
from .logging_extras import create_logger
from .os_utils import remove_dir
from .pikaprint import ColorsHighlight, bold_line, color_line, print_stdout
from .pikspect import YesNo, format_pacman_question, pikspect
from .privilege import sudo
from .prompt import ask_to_continue
from .spawn import interactive_spawn

_debug = create_logger("pkg_cache_cli").debug


def clean_aur_cache() -> None:
    args = parse_args()
    for directory, message, minimal_clean_level in (
            (BuildCachePath(), translate("Build directory"), 1),
            (PackageCachePath(), translate("Packages directory"), 2),
    ):
        print_stdout(f"\n{message}: {directory}")
        question = translate("Do you want to remove all files?")
        if minimal_clean_level > args.clean:
            continue
        if not directory.exists():
            print_stdout(translate("Directory is empty."))
        elif ask_to_continue(
            text=(
                f"{color_line(DECORATION, ColorsHighlight.blue)}"
                f" {bold_line(question)}"
            ),
        ):
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
