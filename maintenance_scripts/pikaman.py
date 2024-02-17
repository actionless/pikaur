"""
NRoff renderer for markdown_it
(C) 2020-today, Y Kirylau

References
----------
    troff/nroff quick reference
    http://www.quut.com/berlin/ms/troff.html

    Basic Formatting with troff/nroff
    by James C. Armstrong and David B. Horvath, CCP
https://cmd.inp.nsk.su/old/cmd2/manuals/unix/UNIX_Unleashed/ch08.htm


"""

import datetime
import inspect
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import markdown_it

if TYPE_CHECKING:
    from collections.abc import MutableMapping, Sequence
    from typing import Any, Final

Token = markdown_it.token.Token
OptionsDict = markdown_it.utils.OptionsDict
OptionsType = markdown_it.utils.OptionsType


class TokenType:
    INLINE: "Final[str]" = "inline"


README_PATH: "Final" = Path(sys.argv[1])
OUTPUT_PATH: "Final" = Path(sys.argv[2])
ENCODING: "Final" = "utf-8"


class NroffRenderer(
        markdown_it.renderer.RendererProtocol,
):
    # pylint: disable=unused-argument

    __output__ = "nroff"
    name: str
    section: int

    def __init__(self, name: str = "test", section: int = 1) -> None:
        super().__init__()
        self.name = name
        self.section = section
        self.rules = {
            k: v
            for k, v in inspect.getmembers(self, predicate=inspect.ismethod)
            if not (k.startswith(("render", "_")))
        }

    def render(
        self, tokens: "Sequence[Token]", options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        result = self.document_open()
        for i, token in enumerate(tokens):
            if token.type == TokenType.INLINE:
                if token.children is None:
                    token_children_is_none_msg = f"{token}.children is `None`."
                    raise RuntimeError(token_children_is_none_msg)
                result += self.render_inline(token.children, options, env)
            elif token.type in self.rules:
                result += self.rules[token.type](tokens, i, options, env)
            else:
                raise NotImplementedError
        return result

    def render_inline(
        self, tokens: "Sequence[Token]", options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        result = ""
        for i, token in enumerate(tokens):
            if token.type in self.rules:
                result += self.rules[token.type](tokens, i, options, env)
            else:
                raise NotImplementedError
        return result

    def text(
            self, tokens: "Sequence[Token]", idx: int,
            options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        return self.escape(tokens[idx].content)

    def softbreak(
            self, tokens: "Sequence[Token]", idx: int,
            options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        return self.escape(" ")

    _html_tag_regex = re.compile("<.*>")

    def html_inline(
            self, tokens: "Sequence[Token]", idx: int,
            options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        text = tokens[idx].content
        text = self._html_tag_regex.sub("", text)
        return self.escape(text)

    def html_block(
            self, tokens: "Sequence[Token]", idx: int,
            options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        return (
            "\n" +
            self.html_inline(tokens, idx, options, env) +
            "\n"
        )

    def heading_open(
            self, tokens: "Sequence[Token]", idx: int,
            options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        token = tokens[idx]
        level = int(token.tag[1])
        sh_tag_max_level = 2
        if level <= sh_tag_max_level:
            return '\n.SH "'
        return '\n.SS "'

    def heading_close(
            self, tokens: "Sequence[Token]", idx: int,
            options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        return '"\n.\n'

    def paragraph_open(
            self, tokens: "Sequence[Token]", idx: int,
            options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        return ".P\n"

    def paragraph_close(
            self, tokens: "Sequence[Token]", idx: int,
            options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        return "\n.\n"

    _last_link: str | None

    def link_open(
            self, tokens: "Sequence[Token]", idx: int,
            options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        token = tokens[idx]
        self._last_link = str(dict(token.attrItems()).get("href", ""))
        return r"\fI"

    def link_close(
            self, tokens: "Sequence[Token]", idx: int,
            options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        result = r"\fR"
        if self._last_link and self.is_url(self._last_link):
            result += (
                " (" +
                self.escape(self._last_link) +
                ")"
            )
        return result

    def image(
            self, tokens: "Sequence[Token]", idx: int,
            options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        return ""

    def code_inline(
            self, tokens: "Sequence[Token]", idx: int,
            options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        token = tokens[idx]
        return (
            r"\fB" +
            self.escape(token.content) +
            r"\fR"
        )

    def bullet_list_open(
            self, tokens: "Sequence[Token]", idx: int,
            options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        return ""

    def bullet_list_close(
            self, tokens: "Sequence[Token]", idx: int,
            options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        return ""

    def list_item_open(
            self, tokens: "Sequence[Token]", idx: int,
            options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        list_deco = r"\(bu"  # bullet
        # bullet_char = node.parent.list_data.get("bullet_char")
        # if bullet_char not in (None, "*"):
        #     list_deco = bullet_char
        return rf'.IP "{list_deco}" 4'

    def list_item_close(
            self, tokens: "Sequence[Token]", idx: int,
            options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        return ".\n"

    # def ordered_list_item(self, token):
    #     list_deco = r"\(bu"  # bullet
    #     # list_deco = node.parent.list_data["start"]
    #     return (
    #         rf'.IP "{list_deco}" 4' +
    #         token.content +
    #         "." +
    #         "\n"
    #     )

    def fence(
            self, tokens: "Sequence[Token]", idx: int,
            options: OptionsDict, env: "MutableMapping[str, str]",
    ) -> str:
        token = tokens[idx]
        return (
            ".nf\n\n" +
            self.escape(token.content) +
            "\n.\n.fi\n"
        )

    # ###################### Helpers: ###################### #

    @staticmethod
    def escape(text: str) -> str:
        for control_character in (".", '"'):
            if text.startswith(control_character):
                text = text.replace(control_character, r"\&" + control_character, 1)
            text = text.replace(r"\n" + control_character, r"\n\&" + control_character)
        return text.replace("-", r"\-").replace("'", r"\'")

    @staticmethod
    def is_url(text: str) -> bool:
        return text.startswith(("http://", "https://"))

    def document_open(self) -> str:
        date = datetime.datetime.now(tz=datetime.UTC).strftime("%B %Y")
        return rf""".\" generated with Pikaman
.
.TH "{self.name.upper()}" "{self.section}" "{date}" "" "{self.name.capitalize()} manual"
.

"""

    # ########################### TBD: ############################### #

    def strong(self, _node: "Any", entering: bool) -> str:  # noqa: FBT001
        if entering:
            return r"\fB"
        return r"\fR"

    def emph(self, _node: "Any", entering: bool) -> str:  # noqa: FBT001
        if entering:
            return r"\fI"
        return r"\fR"


with (
        README_PATH.open(encoding=ENCODING) as input_fobj,
        OUTPUT_PATH.open("w", encoding=ENCODING) as output_fobj,
):
    output_fobj.write(
        NroffRenderer(name="pikaur", section=1).render(
            markdown_it.MarkdownIt().parse(
                input_fobj.read(),
            ),
            options=OptionsDict(options=OptionsType()),  # type: ignore[typeddict-item]
            env={},
        ),
    )
