#!/usr/bin/env python3
#
# pycman-remove - A Python implementation of Pacman
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
A Python implementation of pacman -R

This script uninstalls packages. Various options control
the effect on dependencies of/on given targets.
"""

import sys
from pycman import config
from pycman import transaction

handle = None

def remove(pkgs, options):
	# prepare target list
	db = handle.get_localdb()
	targets = []
	for name in pkgs:
		pkg = db.get_pkg(name)
		if pkg is None:
			print("error: '%s': target not found" % name)
			return 1
		targets.append(pkg)

	t = transaction.init_from_options(handle, options)

	for pkg in targets:
		t.remove_pkg(pkg)

	ok = transaction.finalize(t)
	return (0 if ok else 1)

def main(rawargs):
	global handle
	parser = config.make_parser()
	group = parser.add_argument_group("Remove options")
	group.add_argument('-c', '--cascade',
			action='store_true', default=False,
			help='remove packages and all packages that depend on them')
	group.add_argument('-d', '--nodeps',
			action='store_true', default=False,
			help='skip dependency checks')
	group.add_argument('-k', '--dbonly',
			action='store_true', default=False,
			help='only modify database entries, not package files')
	group.add_argument('-n', '--nosave',
			action='store_true', default=False,
			help='remove configuration files as well')
	group.add_argument('-s', '--recursive',
			action='store_true', default=False,
			help="remove dependencies also (that won't break packages)")
	group.add_argument('-u', '--unneeded',
			action='store_true', default=False,
			help="remove unneeded packages (that won't break packages)")
	group.add_argument('pkgs', metavar='pkg', nargs='*',
			help="a list of packages, e.g. libreoffice, openjdk6")

	args = parser.parse_args(rawargs)
	handle = config.init_with_config_and_options(args)

	if args.verbose:
		print("remove " + " ".join(rawargs), file=sys.stderr)

	if len(args.pkgs) == 0:
		print('error: no targets specified')
		return 1

	return remove(args.pkgs, args)

if __name__ == "__main__":
	ret = main(sys.argv[1:])
	sys.exit(ret)

# vim: set ts=4 sw=4 tw=0 noet:
