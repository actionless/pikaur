#!/usr/bin/env python3
#
# pycman-upgrade - A Python implementation of Pacman
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
A Python implementation of pacman -U

This script installs packages from tarballs. Various options control
the effect of the transaction.
"""

import sys
import pyalpm
from pycman import config
from pycman import transaction

handle = None

def upgrade(pkgs, options):
	# prepare target list
	targets = []
	for name in pkgs:
		pkg = handle.load_pkg(name)
		targets.append(pkg)

	t = transaction.init_from_options(handle, options)

	for pkg in targets:
		t.add_pkg(pkg)

	ok = transaction.finalize(t)
	return (0 if ok else 1)

def main(rawargs):
	global handle
	parser = config.make_parser()
	group = parser.add_argument_group("upgrade options")
	group.add_argument('-d', '--nodeps',
			action='store_true', default=False,
			help='skip dependency checks')
	group.add_argument('-f', '--force',
			action='store_true', default=False,
			help='force install, overwrite conflicting files')
	group.add_argument('-k', '--dbonly',
			action='store_true', default=False,
			help='only modify database entries, not package files')
	group.add_argument('--asdeps', dest='mode',
			action="store_const",
			const=pyalpm.PKG_REASON_DEPEND)
	group.add_argument('--asexplicit', dest='mode',
			action="store_const",
			const=pyalpm.PKG_REASON_EXPLICIT)
	group.add_argument('pkgs', metavar='pkg', nargs='*',
			help="a list of package URLs, e.g. package-1.0-1-x86_64.tar.xz")

	args = parser.parse_args(rawargs)
	handle = config.init_with_config_and_options(args)

	if args.verbose:
		print("upgrade " + " ".join(rawargs), file=sys.stderr)

	return upgrade(args.pkgs, args)

if __name__ == "__main__":
	ret = main(sys.argv[1:])
	sys.exit(ret)

# vim: set ts=4 sw=4 tw=0 noet:
