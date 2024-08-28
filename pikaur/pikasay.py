import argparse
import sys
from typing import Final

from .pikaprint import (
    format_paragraph,
    get_term_width,
    make_equal_right_padding,
    print_stdout,
    printable_length,
    sidejoin_multiline_paragraphs,
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


def bubble_right(
        text: str, margin: int = 1, padding: int = 1, width: int | None = None,
        mascot: str = PIKAPIC,
) -> str:
    enable_vertical_margin = False
    vert_margin = (margin // 2) if enable_vertical_margin else 0
    vert_padding = padding // 2

    bubble_handle = "_\n/"
    bubble_handle_width = len(bubble_handle.splitlines()[0])

    mascot_lines = make_equal_right_padding(mascot).splitlines()

    formatted_paragraph = make_equal_right_padding(
        format_paragraph(
            text,
            padding=padding,
            width=(
                (width or get_term_width())
                - margin * 2
                - padding * 2
                - len(mascot_lines[0])
                - bubble_handle_width
            ),
            force=True,
            split_words=True,
        ),
    )
    paragraph_lines = formatted_paragraph.splitlines()
    paragraph_width = printable_length(paragraph_lines[0])
    paragraph_height = len(paragraph_lines)

    bubble_width = paragraph_width + 2  # formatted paragraph already includes horiz padding
    bubble_height = paragraph_height + 2 + vert_padding * 2

    height_compensating_margin = max(
        0,
        len(mascot_lines) - bubble_height - 2,
    )
    bubble_handle_position = (
        len(mascot_lines)
        + (-5 if bubble_height < len(mascot_lines) else -2)
        - height_compensating_margin
    )

    return (
        f"{' ' * (bubble_width + margin * 2 + bubble_handle_width)}\n"
        * height_compensating_margin
    ) + sidejoin_multiline_paragraphs(
        "",
        "\n".join(
            [" " * margin] * (bubble_height + vert_margin - 1 + 2),
        ),
        "\n".join((
            *([" "] * (vert_margin + 1)),
            "/",
            *(["|"] * (bubble_height - 2)),
            "\\",
        )),
        "\n".join((
            *([" " * (bubble_width - 2)] * vert_margin),
            "_" * (bubble_width - 2),
            *([" " * (bubble_width - 2)] * (vert_padding + 1)),
            formatted_paragraph,
            *([" " * (bubble_width - 2)] * (vert_padding)),
            "_" * (bubble_width - 2),
            *([" " * (bubble_width - 2)] * vert_margin),
        )),
        "\n".join((
            *([" "] * (vert_margin + 1)),
            "\\",
            *(["|"] * (bubble_handle_position)),
            " ",
            *(["|"] * (bubble_height - 2 - bubble_handle_position - 1)),
            "/",
        )),
        "\n".join((
            *([" "] * (vert_margin + 1)),
            *([" "] * (bubble_handle_position)),
            bubble_handle,
            *([" "] * (bubble_height - 2 - bubble_handle_position)),
        )),
        "\n".join(
            [" " * margin] * (bubble_height + vert_margin - 1 + 2),
        ),
    )


def pikasay(  # noqa: PLR0917
        text: str, margin: int = 1, padding: int = 1, width: int | None = None,
        orientation: str = "horizontal", mascot_pic: str = PIKAPIC,
) -> None:
    if orientation == "horizontal":
        message = "".join((
            mascot_pic, bubble_top(text=text, margin=margin, padding=padding, width=width),
        ))
    elif orientation == "vertical":
        message = sidejoin_multiline_paragraphs(
            "",
            bubble_right(text=text, margin=margin, padding=padding, width=width, mascot=mascot_pic),
            mascot_pic,
        )
    else:
        raise ValueError(orientation)
    print_stdout(message)


def pikasay_cli() -> None:
    parser = argparse.ArgumentParser(
        description="⚡️PikaSay",
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
    parser.add_argument(
        "--orientation",
        default="horizontal",
        help="horizontal or vertical",
    )
    args = parser.parse_args()

    text = " ".join(args.text)
    if args.stdin:
        if args.text:
            text += "\n"
        text += "\n".join(line.rstrip("\n") for line in sys.stdin.readlines())
    elif not args.text:
        text = parser.format_help()
    pikasay(
        text, margin=args.margin, padding=args.padding, width=args.width,
        orientation=args.orientation,
    )


if __name__ == "__main__":
    pikasay_cli()
