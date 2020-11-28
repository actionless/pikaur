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

    buf: str
    last_out: str

    def __init__(self, options=None):
        self.options = options or {}
        super().__init__()
        self.name = self.options.get('name', 'test')
        self.section = self.options.get('section', 1)

    def render(self, ast):
        date = datetime.now()
        self.buf = f""".\" generated with Pikaman
.
.TH "{self.name.upper()}" "{self.section}" "{date.strftime("%B")} {date.year}" "" "{self.name.capitalize()} manual"
.
"""
        walker = ast.walker()
        self.last_out = '\n'
        event = walker.nxt()
        while event is not None:
            type_ = event['node'].t
            if hasattr(self, type_):
                getattr(self, type_)(event['node'], event['entering'])
            event = walker.nxt()
        return self.buf

    @staticmethod
    def escape(text):
        return text.replace('-', r'\-').replace("'", r"\'")

    @staticmethod
    def is_url(text):
        return text.startswith('http://') or text.startswith('https://')

    def out(self, s: str):
        self.lit(self.escape(s))

    ####################### Node methods: #######################

    def text(self, node, _entering):
        self.out(node.literal)

    def softbreak(self, _node, _entering):
        self.out(' ')

    def paragraph(self, node, entering):
        gradparent_type = node.parent.parent and node.parent.parent.t
        self.cr()
        if entering:
            if gradparent_type == 'list':
                self.lit(r'.IP "\(bu" 4')
            else:
                self.lit('.P')
        else:
            self.lit('.')
        self.cr()

    def code(self, node, _entering):
        self.lit(r'\fB')
        self.out(node.literal)
        self.lit(r'\fR')

    def code_block(self, node, _entering):
        self.lit('.nf\n\n')
        self.out(node.literal)
        self.lit('\n.\n.fi\n')

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


with open(README_PATH) as fobj:
    with open(OUTPUT_PATH, 'w') as wfobj:
        wfobj.write(
            NroffRenderer(options=dict(name='pikaur')).render(
                commonmark.Parser().parse(
                    fobj.read()
                )
            )
        )
