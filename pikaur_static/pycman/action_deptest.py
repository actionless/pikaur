#!/usr/bin/env python3
#
# pycman-deptest - A Python implementation of Pacman
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
A Python implementation of pacman -T

This script checks whether specified dependencies are satisfied
and prints out a list of those which are missing.
"""

import sys
import pyalpm
from pycman import config

handle = None

def deptest(deps):
	db = handle.get_localdb()
	missing = [dep for dep in deps if pyalpm.find_satisfier(db.pkgcache, dep) is None]
	return missing

def main(rawargs):
	global handle
	parser = config.make_parser()
	parser.add_argument('deps', metavar='dep', nargs='*',
			help="a dependency string, e.g. 'pacman>=3.4.0'")
	args = parser.parse_args(rawargs)
	handle = config.init_with_config_and_options(args)

	if args.verbose:
		print("deptest " + " ".join(rawargs), file=sys.stderr)
	missing = deptest(args.deps)

	if len(missing) == 0:
		return 0
	else:
		[print(dep) for dep in missing]
		return 127

if __name__ == "__main__":
	ret = main(sys.argv[1:])
	sys.exit(ret)

# vim: set ts=4 sw=4 tw=0 noet:
