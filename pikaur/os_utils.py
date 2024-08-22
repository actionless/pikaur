import codecs
import os
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .args import parse_args
from .i18n import translate
from .pikaprint import bold_line, print_error
from .privilege import sudo
from .spawn import interactive_spawn

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Final


READ_MODE: "Final" = "r"


class CodepageSequences:
    UTF_8: "Final[Sequence[bytes]]" = (b"\xef\xbb\xbf", )
    UTF_16: "Final[Sequence[bytes]]" = (b"\xfe\xff", b"\xff\xfe")
    UTF_32: "Final[Sequence[bytes]]" = (b"\xfe\xff\x00\x00", b"\x00\x00\xff\xfe")


def detect_bom_type(file_path: str | Path) -> str:
    """
    returns file encoding string for open() function
    https://stackoverflow.com/a/44295590/1850190
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)
    with file_path.open("rb") as test_file:
        first_bytes = test_file.read(4)

    if first_bytes[0:3] in CodepageSequences.UTF_8:
        return "utf-8"

    # Python automatically detects endianness if utf-16 bom is present
    # write endianness generally determined by endianness of CPU
    if first_bytes[0:2] in CodepageSequences.UTF_16:
        return "utf16"

    if first_bytes[0:5] in CodepageSequences.UTF_32:
        return "utf32"

    # If BOM is not provided, then assume its the codepage
    #     used by your operating system
    return "cp1252"
    # For the United States its: cp1252


def open_file(
        file_path: str | Path, mode: str = READ_MODE, encoding: str | None = None,
) -> codecs.StreamReaderWriter:
    if encoding is None and (mode and READ_MODE in mode):
        encoding = detect_bom_type(file_path)
    try:
        if encoding:
            return codecs.open(  # noqa: SIM115
                str(file_path), mode, errors="ignore", encoding=encoding,
            )
        return codecs.open(  # noqa: SIM115
            str(file_path), mode, errors="ignore",
        )
    except PermissionError:
        print_error()
        print_error(translate("Error opening file: {file_path}").format(file_path=file_path))
        print_error()
        raise


def replace_file(src: str | Path, dest: str | Path) -> None:
    if isinstance(src, str):
        src = Path(src)
    if isinstance(dest, str):
        dest = Path(dest)
    if src.exists():
        if dest.exists():
            dest.unlink()
        shutil.move(src, dest)


def remove_dir(dir_path: str | Path) -> None:
    try:
        shutil.rmtree(dir_path)
    except PermissionError:
        interactive_spawn(sudo(["rm", "-rf", str(dir_path)]))


def dirname(path: str | Path) -> Path:
    return Path(path).parent if path else Path()


def check_executables(dep_names: list[str]) -> None:
    for dep_bin in dep_names:
        if not shutil.which(dep_bin):
            message = translate("executable not found")
            print_error(
                f"'{bold_line(dep_bin)}' {message}.",
            )
            sys.exit(2)


def chown_to_current(path: Path) -> None:
    args = parse_args()
    user_id = args.user_id
    if user_id:
        if not isinstance(user_id, int):
            raise TypeError
        try:
            os.chown(path, user_id, user_id)
        except PermissionError as exc:
            print_error()
            print_error(
                translate("Can't change owner to {user_id}: {exc}").format(
                    user_id=user_id, exc=exc,
                ),
            )
            print_error()


def mkdir(path: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True)
    chown_to_current(path)
