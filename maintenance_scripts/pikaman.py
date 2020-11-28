"""
NRoff renderer for CommonMark
(C) 2020 Y Kirylau

References:
    troff/nroff quick reference
    http://www.quut.com/berlin/ms/troff.html

    Basic Formatting with troff/nroff
    by James C. Armstrong and David B. Horvath, CCP
    https://cmd.inp.nsk.su/old/cmd2/manuals/unix/UNIX_Unleashed/ch08.htm
"""

import sys
from datetime import datetime

import commonmark


README_PATH = sys.argv[1]
OUTPUT_PATH = sys.argv[2]


class NroffRenderer(commonmark.render.renderer.Renderer):

    def __init__(self, options=None):
        self.options = options or {}
        super().__init__()
        self.name = self.options.get('name', 'test')
        self.section = self.options.get('section', 1)

    @staticmethod
    def escape(text):
        return text.replace('-', r'\-').replace("'", r"\'")

    @staticmethod
    def is_url(text):
        return text.startswith('http://') or text.startswith('https://')

    def out(self, s: str):
        self.lit(self.escape(s))

    ####################### Node methods: #######################

    # Note: it's intentionally not implementing `image` node handler.
    #       While `list` and `item` types are handled by `paragraph()`.

    def document(self, _node, entering):
        if entering:
            self.lit(rf""".\" generated with Pikaman
.
.TH "{self.name.upper()}" "{self.section}" "{datetime.now().strftime("%B %Y")}" "" "{self.name.capitalize()} manual"
.
""")

    def text(self, node, _entering):
        self.out(node.literal)

    def softbreak(self, _node, _entering):
        self.out(' ')

    def paragraph(self, node, entering):
        gradparent_type = node.parent.parent and node.parent.parent.t
        self.cr()
        if entering:
            if gradparent_type == 'list':
                list_deco = r"\(bu"  # bullet
                if node.parent.list_data.get('type') == 'ordered':
                    list_deco = node.parent.list_data['start']
                else:
                    bullet_char = node.parent.list_data.get('bullet_char')
                    if bullet_char not in (None, '*'):
                        list_deco = bullet_char
                self.lit(rf'.IP "{list_deco}" 4')
            else:
                self.lit('.P')
        else:
            self.lit('.')
        self.cr()

    def strong(self, _node, entering):
        if entering:
            self.lit(r'\fB')
        else:
            self.lit(r'\fR')

    def code(self, node, _entering):
        self.lit(r'\fB')
        self.out(node.literal)
        self.lit(r'\fR')

    def code_block(self, node, _entering):
        self.lit('.nf\n\n')
        self.out(node.literal)
        self.lit('\n.\n.fi\n')

    def emph(self, _node, entering):
        if entering:
            self.lit(r'\fI')
        else:
            self.lit(r'\fR')

    def link(self, node, entering):
        if entering:
            self.lit(r'\fI')
        else:
            self.lit(r'\fR')
            if self.is_url(node.destination):
                self.lit(' (')
                self.out(node.destination)
                self.lit(')')

    def heading(self, node, entering):
        if entering:
            if node.level <= 2:
                self.lit('.SH "')
            else:
                self.lit('.SS "')
        else:
            self.lit('"\n.\n')


with open(README_PATH) as input_fobj:
    with open(OUTPUT_PATH, 'w') as output_fobj:
        output_fobj.write(
            NroffRenderer(options=dict(name='pikaur', section=1)).render(
                commonmark.Parser().parse(
                    input_fobj.read()
                )
            )
        )
