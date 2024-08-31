#!/usr/bin/env python3
#
# pycman-version - A Python implementation of Pacman
# Copyright (C) 2011 Rémy Oudompheng <remy@archlinux.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#

"""
A Python implementation of pacman -V

This script prints version information about pycman and pyalpm.
"""

import pyalpm

VERSION_STRING = """
                       Pycman running on pyalpm v%s - libalpm v%s
 .--.
/ _.-' .-.  .-.  .-.   libalpm:
\\  '-. '-'  '-'  '-'     Copyright (C) 2006-2011 Pacman Development Team
 '--'                    Copyright (C) 2002-2006 Judd Vinet
                       pyalpm:
                         Copyright (C) 2011 Rémy Oudompheng

                       This program may be freely redistributed under
                       the terms of the GNU General Public License.
"""

def main(args):
	print(VERSION_STRING % (pyalpm.version(), pyalpm.alpmversion()))
	return 2

if __name__ == "__main__":
	import sys
	ret = main(sys.argv[1:])
	sys.exit(ret)

# vim: set ts=4 sw=4 tw=0 noet:
