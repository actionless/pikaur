"""
NRoff renderer for CommonMark
(C) 2020-today, Y Kirylau

References:
    troff/nroff quick reference
    http://www.quut.com/berlin/ms/troff.html

    Basic Formatting with troff/nroff
    by James C. Armstrong and David B. Horvath, CCP
    https://cmd.inp.nsk.su/old/cmd2/manuals/unix/UNIX_Unleashed/ch08.htm
"""

import inspect
import re
import sys
from collections.abc import MutableMapping
from datetime import datetime
from typing import Sequence, Optional

import markdown_it

Token = markdown_it.token.Token
OptionsDict = markdown_it.utils.OptionsDict

README_PATH = sys.argv[1]
OUTPUT_PATH = sys.argv[2]
ENCODING = 'utf-8'


class NroffRenderer(markdown_it.renderer.RendererProtocol):  # pylint: disable=too-many-public-methods

    __output__ = 'nroff'

    def __init__(self, options=None):
        self.options = options or {}
        super().__init__()
        self.name = self.options.get('name', 'test')
        self.section = self.options.get('section', 1)
        self.rules = {
            k: v
            for k, v in inspect.getmembers(self, predicate=inspect.ismethod)
            if not (k.startswith("render") or k.startswith("_"))
        }

    def render(
        self, tokens: Sequence[Token], options: OptionsDict, env: MutableMapping
    ) -> str:
        result = self.document_open()
        for i, token in enumerate(tokens):
            if token.type == "inline":
                assert token.children is not None
                result += self.render_inline(token.children, options, env)
            elif token.type in self.rules:
                result += self.rules[token.type](tokens, i, options, env)
            else:
                raise NotImplementedError()
        return result

    def render_inline(
        self, tokens: Sequence[Token], options: OptionsDict, env: MutableMapping
    ) -> str:
        result = ""
        for i, token in enumerate(tokens):
            if token.type in self.rules:
                result += self.rules[token.type](tokens, i, options, env)
            else:
                raise NotImplementedError()
        return result

    def text(
            self, tokens: Sequence[Token], idx: int,
            options: OptionsDict, env: MutableMapping
    ):
        return self.escape(tokens[idx].content)

    def softbreak(
            self, tokens: Sequence[Token], idx: int,
            options: OptionsDict, env: MutableMapping
    ):
        return self.escape(' ')

    _html_tag_regex = re.compile('<.*>')

    def html_inline(
            self, tokens: Sequence[Token], idx: int,
            options: OptionsDict, env: MutableMapping
    ):
        text = tokens[idx].content
        text = self._html_tag_regex.sub('', text)
        return self.escape(text)

    def html_block(
            self, tokens: Sequence[Token], idx: int,
            options: OptionsDict, env: MutableMapping
    ):
        return (
            "\n" +
            self.html_inline(tokens, idx, options, env) +
            "\n"
        )

    def heading_open(
            self, tokens: Sequence[Token], idx: int,
            options: OptionsDict, env: MutableMapping
    ):
        token = tokens[idx]
        level = int(token.tag[1])
        if level <= 2:
            return '\n.SH "'
        return '\n.SS "'

    def heading_close(
            self, tokens: Sequence[Token], idx: int,
            options: OptionsDict, env: MutableMapping
    ):
        return '"\n.\n'

    def paragraph_open(
            self, tokens: Sequence[Token], idx: int,
            options: OptionsDict, env: MutableMapping
    ):
        return '.P\n'

    def paragraph_close(
            self, tokens: Sequence[Token], idx: int,
            options: OptionsDict, env: MutableMapping
    ):
        return '\n.\n'

    _last_link: Optional[str]

    def link_open(
            self, tokens: Sequence[Token], idx: int,
            options: OptionsDict, env: MutableMapping
    ):
        token = tokens[idx]
        self._last_link = str(dict(token.attrItems()).get('href', ''))
        return r'\fI'

    def link_close(
            self, tokens: Sequence[Token], idx: int,
            options: OptionsDict, env: MutableMapping
    ):
        result = r'\fR'
        if self._last_link and self.is_url(self._last_link):
            result += (
                ' (' +
                self.escape(self._last_link) +
                ')'
            )
        return result

    def image(
            self, tokens: Sequence[Token], idx: int,
            options: OptionsDict, env: MutableMapping
    ):
        return ''

    def code_inline(
            self, tokens: Sequence[Token], idx: int,
            options: OptionsDict, env: MutableMapping
    ):
        token = tokens[idx]
        return (
            r'\fB' +
            self.escape(token.content) +
            r'\fR'
        )

    def bullet_list_open(
            self, tokens: Sequence[Token], idx: int,
            options: OptionsDict, env: MutableMapping
    ):
        return ''

    def bullet_list_close(
            self, tokens: Sequence[Token], idx: int,
            options: OptionsDict, env: MutableMapping
    ):
        return ''

    def list_item_open(
            self, tokens: Sequence[Token], idx: int,
            options: OptionsDict, env: MutableMapping
    ):
        list_deco = r"\(bu"  # bullet
        # bullet_char = node.parent.list_data.get('bullet_char')
        # if bullet_char not in (None, '*'):
        #     list_deco = bullet_char
        return rf'.IP "{list_deco}" 4'

    def list_item_close(
            self, tokens: Sequence[Token], idx: int,
            options: OptionsDict, env: MutableMapping
    ):
        return '.\n'

    # def ordered_list_item(self, token):
    #     list_deco = r"\(bu"  # bullet
    #     # list_deco = node.parent.list_data['start']
    #     return (
    #         rf'.IP "{list_deco}" 4' +
    #         token.content +
    #         '.' +
    #         "\n"
    #     )

    def fence(
            self, tokens: Sequence[Token], idx: int,
            options: OptionsDict, env: MutableMapping
    ):
        token = tokens[idx]
        return (
            '.nf\n\n' +
            self.escape(token.content) +
            '\n.\n.fi\n'
        )

    # ###################### Helpers: ###################### #

    @staticmethod
    def escape(text):
        for control_character in ('.', '"'):
            if text.startswith(control_character):
                text = text.replace(control_character, r'\&' + control_character, 1)
            text = text.replace(r'\n' + control_character, r'\n\&' + control_character)
        return text.replace('-', r'\-').replace("'", r"\'")

    @staticmethod
    def is_url(text):
        return text.startswith('http://') or text.startswith('https://')

    def document_open(self):
        return rf""".\" generated with Pikaman
.
.TH "{self.name.upper()}" "{self.section}" "{datetime.now().strftime("%B %Y")}" "" "{self.name.capitalize()} manual"
.

"""

    # ########################### TBD: ############################### #

    def strong(self, _node, entering):
        if entering:
            return r'\fB'
        return r'\fR'

    def emph(self, _node, entering):
        if entering:
            return r'\fI'
        return r'\fR'


with open(README_PATH, encoding=ENCODING) as input_fobj:
    with open(OUTPUT_PATH, 'w', encoding=ENCODING) as output_fobj:
        output_fobj.write(
            NroffRenderer(options=dict(name='pikaur', section=1)).render(
                markdown_it.MarkdownIt().parse(
                    input_fobj.read()
                ),
                options=OptionsDict(),
                env={}
            )
        )
