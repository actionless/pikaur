import sys
from typing import Final

from .pikaprint import format_paragraph, get_term_width, make_equal_right_padding

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


def bubble_top(text: str, padding: int = 1) -> str:
    bubble_top_left = " _____/|"
    formatted_paragraph = make_equal_right_padding(
        format_paragraph(
            text, padding=1, width=get_term_width() - 4 - padding * 2,
            force=True, split_words=True,
        ),
    )
    paragraph_width = len(formatted_paragraph.splitlines()[0])
    max_string_length = max(paragraph_width, len(bubble_top_left) + 1)
    if paragraph_width < max_string_length:
        formatted_paragraph += " " * (max_string_length - paragraph_width)
    return "".join((
        " " * padding,
        bubble_top_left,
        "_" * (max_string_length - len(bubble_top_left) + 1),
        " " * padding,
        "\n",

        " " * padding,
        "/",
        " " * max_string_length,
        "\\",
        " " * padding,
        "\n",

        *(f"{' ' * padding}|{line}|{' ' * padding}\n" for line in formatted_paragraph.splitlines()),

        " " * padding,
        "\\",
        "_" * max_string_length,
        "/",
        " " * padding,
        "\n",
    ))


def pikasay(text: str) -> None:
    sys.stdout.write("".join((
        PIKAPIC, bubble_top(text),
    )))


def pikasay_cli() -> None:
    text = " ".join(sys.argv[1:])
    if (text in {"-", ""}) or (not sys.stdin.isatty()):
        if text in {"-", ""}:
            text = ""
        else:
            text += "\n"
        text += "\n".join(line.rstrip("\n") for line in sys.stdin.readlines())
    pikasay(text)


if __name__ == "__main__":
    pikasay_cli()
