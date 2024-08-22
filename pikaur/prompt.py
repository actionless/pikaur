"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import os
import shutil
import sys
import tty
from typing import TYPE_CHECKING

from .args import LiteralArgs, parse_args
from .config import PikaurConfig, PromptLockPath
from .exceptions import SysExit
from .filelock import FileLock
from .i18n import translate
from .logging_extras import create_logger
from .pikaprint import (
    ColorsHighlight,
    TTYRestoreContext,
    color_line,
    get_term_width,
    print_stderr,
    print_warning,
    range_printable,
)
from .pikspect import PikspectPopen, ReadlineKeycodes, TTYInputWrapper
from .pikspect import pikspect as pikspect_spawn
from .privilege import isolate_root_cmd
from .spawn import InteractiveSpawn, interactive_spawn

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from typing import Final


logger = create_logger("prompt")
logger_no_lock = create_logger("prompt_nolock", lock=False)


class Answers:

    _init_done: bool = False
    Y: str  # pylint: disable=invalid-name
    N: str  # pylint: disable=invalid-name
    Y_UP: str
    N_UP: str

    @classmethod
    def _do_init(cls) -> None:
        if not cls._init_done:
            cls.Y = translate("y")
            cls.N = translate("n")
            cls.Y_UP = cls.Y.upper()
            cls.N_UP = cls.N.upper()
            cls._init_done = True

    def __init__(self) -> None:
        self._do_init()


def read_answer_from_tty(question: str, answers: "Sequence[str] | None" = None) -> str:
    """
    Function displays a question and reads a single character
    from STDIN as an answer. Then returns the character as lower character.
    Valid answers are passed as 'answers' variable (the default is in capital).
    Invalid answer will return an empty string.
    """
    default = " "
    all_answers = Answers()
    answers = answers or (all_answers.Y_UP, all_answers.N)

    for letter in answers:
        if letter.isupper():
            default = letter.lower()
            break

    if not sys.stdin.isatty():
        return default

    print_stderr(question, flush=True, end=" ", lock=False)
    previous_tty_settings = tty.tcgetattr(sys.stdin.fileno())  # type: ignore[attr-defined]
    try:
        tty.setraw(sys.stdin.fileno())
        answer = sys.stdin.read(1).lower()
    except Exception:
        return " "
    else:
        if ord(answer) in {ReadlineKeycodes.CTRL_C, ReadlineKeycodes.CTRL_D}:
            raise SysExit(1)
        if ord(answer) == ReadlineKeycodes.ENTER:
            answer = default
            return default
        if answer in [choice.lower() for choice in answers]:
            return answer
        return " "
    finally:
        tty.tcsetattr(  # type: ignore[attr-defined]
            sys.stdin.fileno(), tty.TCSADRAIN, previous_tty_settings,  # type: ignore[attr-defined]
        )
        sys.stdout.write(f"{answer}\r\n")
        tty.tcdrain(sys.stdin.fileno())  # type: ignore[attr-defined]


def split_last_line(text: str) -> str:
    all_lines = text.split("\n")
    n_lines = len(all_lines)
    last_line = all_lines[n_lines - 1]
    term_width = get_term_width()
    if len(last_line) < term_width:
        return text
    prev_lines = all_lines[:n_lines - 1]
    return "\n".join([
        *prev_lines,
        range_printable(last_line, 0, term_width),
        range_printable(last_line, term_width),
    ])


def get_input(
        prompt: str, answers: "Sequence[str]" = (), *, require_confirm: bool = False,
) -> str:
    logger.debug("Gonna get input from user...")
    answer = ""
    with (
            FileLock(PromptLockPath()),
            TTYInputWrapper(),
            TTYRestoreContext(before=True, after=True),
    ):
        if not (
                require_confirm or PikaurConfig().ui.RequireEnterConfirm.get_bool()
        ):
            logger_no_lock.debug("Using custom input reader...")
            answer = read_answer_from_tty(prompt, answers=answers)
        else:
            logger_no_lock.debug("Restoring TTY...")
            try:
                logger_no_lock.debug("Using standard input reader...")
                answer = input(split_last_line(prompt)).lower()
            except EOFError as exc:
                logger_no_lock.debug(exc)
                raise SysExit(125) from exc

    if not answer:
        for choice in answers:
            if choice.isupper():
                logger.debug('No answer provided - using "{}".', choice)
                return choice.lower()
    logger.debug("Got answer: '{}'", answer)
    return answer


class NotANumberInputError(Exception):
    character: str

    def __init__(self, character: str) -> None:
        self.character = character
        super().__init__(f'"{character} is not a number')


class NumberRangeInputSyntax:
    DELIMITERS: "Final[Sequence[str]]" = (" ", ",")
    RANGES: "Final[Sequence[str]]" = ("-", "..")


def get_multiple_numbers_input(prompt: str = "> ", answers: "Iterable[int]" = ()) -> list[int]:
    str_result = get_input(prompt, [str(answer) for answer in answers], require_confirm=True)
    if not str_result:
        return []
    for delimiter in NumberRangeInputSyntax.DELIMITERS[1:]:
        str_result = str_result.replace(delimiter, NumberRangeInputSyntax.DELIMITERS[0])
    str_results = str_result.split(NumberRangeInputSyntax.DELIMITERS[0])
    int_results: list[int] = []
    for raw_block in str_results[:]:
        block = raw_block
        for range_char in NumberRangeInputSyntax.RANGES:
            block = block.replace(range_char, NumberRangeInputSyntax.RANGES[0])
        if NumberRangeInputSyntax.RANGES[0] in block:
            try:
                range_start, range_end = (
                    int(char) for char in block.split(NumberRangeInputSyntax.RANGES[0], maxsplit=1)
                )
            except ValueError as exc:
                raise NotANumberInputError(block) from exc
            if range_start > range_end:
                raise NotANumberInputError(block)
            int_results += list(range(range_start, range_end + 1))
        else:
            try:
                int_results.append(int(block))
            except ValueError as exc:
                raise NotANumberInputError(exc.args[0].split("'")[-2]) from exc
    return int_results


def ask_to_continue(text: str | None = None, *, default_yes: bool = True) -> bool:
    args = parse_args()
    if text is None:
        text = translate("Do you want to proceed?")

    if args.noconfirm:
        default_option = translate(
            "[Y]es ({reason})"
            if default_yes else
            "[N]o ({reason})",
        ).format(reason=LiteralArgs.NOCONFIRM)
        print_stderr(f"{text} {default_option}")
        return default_yes

    all_answers = Answers()
    prompt = text + (
        f" [{all_answers.Y_UP}/{all_answers.N}] " if default_yes else
        f" [{all_answers.Y}/{all_answers.N_UP}] "
    )
    answers = (
        (all_answers.Y_UP + all_answers.N) if default_yes else
        (all_answers.Y + all_answers.N_UP)
    )

    answer = get_input(prompt, answers)
    return (answer == all_answers.Y) or (default_yes and not answer)


def retry_interactive_command(
        cmd_args: list[str],
        *,
        pikspect: bool = False,
        conflicts: list[list[str]] | None = None,
) -> bool:
    args = parse_args()
    while True:
        proc: InteractiveSpawn | PikspectPopen = (
            pikspect_spawn(
                cmd_args,
                conflicts=conflicts,
            )
            if pikspect and (LiteralArgs.NOCONFIRM not in cmd_args) else
            interactive_spawn(
                cmd_args,
            )
        )
        good = proc.returncode == 0
        if good:
            return good
        print_stderr(color_line(
            translate("Command '{}' failed to execute.").format(
                " ".join(cmd_args),
            ),
            ColorsHighlight.red,
        ))
        if not ask_to_continue(
                text=translate("Do you want to retry?"),
                default_yes=not args.noconfirm,
        ):
            return False


def retry_interactive_command_or_exit(
        cmd_args: list[str],
        *,
        pikspect: bool = False,
        conflicts: list[list[str]] | None = None,
) -> None:
    if not retry_interactive_command(
            cmd_args,
            pikspect=pikspect,
            conflicts=conflicts,
    ) and not ask_to_continue(default_yes=False):
        raise SysExit(125)


def get_editor() -> list[str] | None:
    editor_line = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    logger.debug("Found editor: {}", editor_line)
    if editor_line:
        return editor_line.split(" ")
    for editor in (
            "vim", "nano", "mcedit", "edit", "emacs", "nvim", "kak",
            "e3", "atom", "adie", "dedit", "gedit", "jedit", "kate", "kwrite", "leafpad",
            "mousepad", "notepadqq", "pluma", "code", "xed", "geany",
    ):
        path = shutil.which(editor)
        logger.debug("Editor not set, defaulting to: {} ({})", editor, path)
        if path:
            return [path]
    logger.debug("No editor found!")
    return None


def get_editor_or_exit() -> list[str] | None:
    editor = get_editor()
    if not editor:
        print_warning(translate("no editor found. Try setting $VISUAL or $EDITOR."))
        if not ask_to_continue(
                translate("Do you want to proceed without editing?"),
        ):  # pragma: no cover
            raise SysExit(125)
    if not isinstance(editor, list):  # mypy 🙄
        raise TypeError
    return isolate_root_cmd(editor) if parse_args().user_id else editor
