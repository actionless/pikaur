import argparse
import sys
from typing import Final

from .pikaprint import (
    format_paragraph,
    get_term_width,
    make_equal_right_padding,
    print_stdout,
    printable_length,
)

PIKAPIC: Final = r"""
      /:}               _
     /--1             / :}
    /   |           / `-/
   |  ,  --------  /   /
   |'                 Y
  /                   l
  l  /       \        l
  j  ●   .   ●        l
 { )  ._,.__,   , -.  {
  Y    \  _/     ._/   \

"""


def bubble_top(
        text: str, margin: int = 1, padding: int = 1, width: int | None = None,
) -> str:
    bubble_top_left = " _____/|"
    formatted_paragraph = make_equal_right_padding(
        format_paragraph(
            text,
            padding=padding,
            width=(width or get_term_width()) - margin * 2 - padding * 2,
            force=True,
            split_words=True,
        ),
    )
    paragraph_width = printable_length(formatted_paragraph.splitlines()[0])
    max_string_length = max(paragraph_width, len(bubble_top_left) + 1)
    if paragraph_width < max_string_length:
        formatted_paragraph = make_equal_right_padding(
            formatted_paragraph, max_string_length,
        )
    return "".join((
        " " * margin,
        bubble_top_left,
        "_" * (max_string_length - len(bubble_top_left) + 1),
        " " * margin,
        "\n",

        " " * margin,
        "/",
        " " * max_string_length,
        "\\",
        " " * margin,
        "\n",

        f"{' ' * margin}|{' ' * max_string_length}|{' ' * margin}\n" * ((padding - 1) // 2),
        *(f"{' ' * margin}|{line}|{' ' * margin}\n" for line in formatted_paragraph.splitlines()),
        f"{' ' * margin}|{' ' * max_string_length}|{' ' * margin}\n" * ((padding - 1) // 2),

        " " * margin,
        "\\",
        "_" * max_string_length,
        "/",
        " " * margin,
    ))


def pikasay(
        text: str, margin: int = 1, padding: int = 1, width: int | None = None,
) -> None:
    print_stdout("".join((
        PIKAPIC, bubble_top(text=text, margin=margin, padding=padding, width=width),
    )))


def pikasay_cli() -> None:
    parser = argparse.ArgumentParser(
        description="⚡️⚡️PikaSay",
    )
    parser.add_argument(
        "text",
        nargs="*",
        help="text to print",
    )
    parser.add_argument(
        "-",
        dest="stdin",
        default=(not sys.stdin.isatty()),
        action="store_true",
        help="read from stdin",
    )
    parser.add_argument(
        "--margin",
        type=int,
        default=1,
        help="text bubble margin",
    )
    parser.add_argument(
        "--padding",
        type=int,
        default=2,
        help="text bubble padding",
    )
    parser.add_argument(
        "--width",
        type=int,
        help="force terminal width",
    )
    args = parser.parse_args()

    text = " ".join(args.text)
    if args.stdin:
        if args.text:
            text += "\n"
        text += "\n".join(line.rstrip("\n") for line in sys.stdin.readlines())
    elif not args.text:
        pikasay(parser.format_help(), margin=args.margin, padding=args.padding, width=args.width)
        sys.exit(0)
    pikasay(text, margin=args.margin, padding=args.padding, width=args.width)


if __name__ == "__main__":
    pikasay_cli()
