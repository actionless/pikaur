#!/usr/bin/env python3
#
# pycman-query - A Python implementation of Pacman
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
A Python implementation of pacman -Q

This script displays information about installed packages.
"""

import os
import sys

import pyalpm
from pycman import config
from pycman import pkginfo

handle = None

def filter_pkglist(pkglist, options):
	result = []
	if options.foreign:
		syncpkgs = set()
		for db in handle.get_syncdbs():
			syncpkgs |= set(p.name for p in db.pkgcache)
	for pkg in pkglist:
		if options.deps and pkg.reason == pyalpm.PKG_REASON_EXPLICIT:
			continue
		if options.explicit and pkg.reason == pyalpm.PKG_REASON_DEPEND:
			continue
		if options.unrequired and len(pkg.compute_requiredby()) > 0:
			continue
		if options.foreign and pkg.name in syncpkgs:
			continue
		if options.upgrades and pyalpm.sync_newversion(pkg, handle.get_syncdbs()) is None:
			continue
		result.append(pkg)
	return result

def display_pkg(pkg, options):
	displaystyle = 'file' if options.package else 'local'
	if options.info > 0:
		pkginfo.display_pkginfo(pkg, level=options.info, style=displaystyle)
	elif not options.listfiles:
		if options.quiet:
			print(pkg.name)
		else:
			print(pkg.name, pkg.version)

	if options.listfiles:
		if options.quiet:
			[print('/' + path) for path, size, mode in pkg.files]
		else:
			[print(pkg.name, '/' + path) for path, size, mode in pkg.files]

def find_file(filenames, options):
	"lookup for files in local packages"
	ret = 0
	if len(filenames) == 0:
		print("error: no targets specified")
		ret = 1

	localpkgs = handle.get_localdb().pkgcache

	for name in filenames:
		lookupname = None
		if not os.path.isabs(name):
			# lookup in PATH
			for dirname in os.getenv('PATH').split(':'):
				if os.path.lexists(os.path.join(dirname, name)):
					name = os.path.join(dirname, name)
					lookupname = name
			if lookupname is None:
				print("error: failed to find '%s' in PATH: No such file or directory" % name)
				ret = 1
				continue
		else:
			if not os.path.lexists(name):
				print("error: failed to read file '%s': No such file or directory" % name)
				ret = 1
				continue
			lookupname = name
		lookupname = os.path.normpath(lookupname)
		lookupname = lookupname.lstrip('/')
		found = False
		for pkg in localpkgs:
			files = pkg.files

			if any(f for f in files if lookupname == f[0]):
				if options.quiet:
					print(pkg.name)
				else:
					print(pkg.name, "is owned by", pkg.name, pkg.version)
				found = True
				break

		if not found:
			print('error: no package owns', name)
			ret = 1

	return ret

def find_search(patterns, options):
	db = handle.get_localdb()
	results = db.search(*patterns)
	if len(results) == 0:
		return 1
	for pkg in results:
		if options.quiet:
			print(pkg.name)
		else:
			print("%s/%s %s" % (pkg.db.name, pkg.name, pkg.version))
			print("    " + pkg.desc)
	return 0

def main(rawargs):
	global handle
	parser = config.make_parser(prog='pycman-query')
	group = parser.add_argument_group("Query options")
	group.add_argument('-d', '--deps',
			action='store_true', default=False,
			help='list packages installed as dependencies [filter]')
	group.add_argument('-e', '--explicit',
			action='store_true', default=False,
			help='list packages explicitly installed [filter]')
	group.add_argument('-i', '--info',
			action='count', dest='info', default=0,
			help='view package information')
	group.add_argument('-l', '--list',
			action='store_true', dest='listfiles', default=False,
			help='list the contents of the queried package')
	group.add_argument('-m', '--foreign',
			action='store_true', default=False,
			help='list installed packages not found in sync db(s) [filter]')
	group.add_argument('-o', '--owns',
			action='store_true', default=False,
			help='query the package that owns <file>')
	group.add_argument('-p', '--package',
			action='store_true', default=False,
			help='query a package file instead of the database')
	group.add_argument('-q', '--quiet',
			action='store_true', dest='quiet', default=False,
			help='show less information for query and search')
	group.add_argument('-s', '--search', action='store_true', default=False,
			help='search locally-installed packages for matching strings')
	group.add_argument('-t', '--unrequired',
			action='store_true', default=False,
			help="list packages not required by any package [filter]")
	group.add_argument('-u', '--upgrades',
			action='store_true', default=False,
			help="list outdated packages [filter]")
	group.add_argument('pkgnames', metavar='pkg', nargs='*',
			help='packages to show (show all packages if no arguments) '
			'(when used with -o: a filename, '
			'when used with -p: the path to a package file)')

	args = parser.parse_args(rawargs)
	handle = config.init_with_config_and_options(args)

	if args.verbose:
		print("query " + " ".join(rawargs), file=sys.stderr)

	db = handle.get_localdb()
	retcode = 0

	# actions other than listing packages
	if args.owns:
		return find_file(args.pkgnames, args)
	if args.search:
		return find_search(args.pkgnames, args)

	pkglist = []
	if len(args.pkgnames) > 0:
		# a list of package names was specified
		for pkgname in args.pkgnames:
			if args.package:
				pkg = handle.load_pkg(pkgname)
			else:
				pkg = db.get_pkg(pkgname)
			if pkg is None:
				print('error: package "%s" not found' % pkgname)
				retcode = 1
			else:
				pkglist.append(pkg)
	else:
		# no package was specified, display all
		pkglist = db.pkgcache
	# determine the list of package to actually display
	pkglist = filter_pkglist(pkglist, args)
	for pkg in pkglist:
		display_pkg(pkg, args)

	return retcode

if __name__ == "__main__":
	ret = main(sys.argv[1:])
	sys.exit(ret)

# vim: set ts=4 sw=4 tw=0 noet:
