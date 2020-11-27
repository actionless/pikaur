"""
Licensed under GPLv3
(C) 2020 Y Kirylau
"""

import sys

import commonmark


README_PATH = sys.argv[1]
OUTPUT_PATH = sys.argv[2]


PREFIX = """.\" generated with Pikaman
.\" Licensed under GPLv3
.
.TH "PIKAUR" "1" "November 2020" "" "Pikaur manual"
.
"""


class NroffRenderer(commonmark.render.renderer.Renderer):

    @staticmethod
    def escape(text):
        return text.replace('-', r'\-').replace("'", r"\'")

    def text_out(self, text):
        self.out(self.escape(text))

    def text(self, node, _entering=None):
        parent_type = node.parent and node.parent.t
        if parent_type == "heading":
            # self.out('''.SH "''')
            self.text_out(node.literal)
            # self.out('''"
# .''')
        else:
            self.text_out(node.literal)

    def softbreak(self, _node, _entering):
        self.out(' ')

    def paragraph(self, node, entering):
        gradparent_type = node.parent.parent and node.parent.parent.t
        self.cr()
        if entering:
            if gradparent_type == 'list':
                self.out(r'.IP "\(bu" 4')
            else:
                self.out('.P')
        else:
            self.out('.')
        self.cr()

    def code(self, node, _entering):
        self.out(r'\fB')
        self.text_out(node.literal)
        self.out(r'\fR')

    def code_block(self, node, _entering):
        self.out('''.nf

''')
        self.text_out(node.literal)
        self.out('''
.
.fi
''')

    def link(self, node, entering):
        if entering:
            self.out(r'\fI')
        else:
            self.out(r'\fR')
            if node.destination and node.destination.startswith('http'):
                self.out(' (')
                self.text_out(node.destination)
                self.out(')')

    def heading(self, node, entering):
        if entering:
            if node.level <= 2:
                self.out('.SH "')
            else:
                self.out('.SS "')
        else:
            self.out('''"
.
''')


with open(README_PATH) as fobj:
    nroff = PREFIX + NroffRenderer().render(
        commonmark.Parser().parse(fobj.read())
    )
    with open(OUTPUT_PATH, 'w') as wfobj:
        wfobj.write(nroff)
