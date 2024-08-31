#!/usr/bin/env python3
#
# pycman-sync - A Python implementation of Pacman
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
A Python implementation of pacman -S

This script displays information about packages available in repositories,
and is also used to install/upgrade/remove them.
"""

import sys

import pyalpm
from pycman import config
from pycman import pkginfo
from pycman import transaction

handle = None

def do_clean(options):
	raise NotImplementedError

def do_refresh(options):
	"Sync databases like pacman -Sy"
	force = (options.refresh > 1)
	for db in handle.get_syncdbs():
		t = transaction.init_from_options(handle, options)
		db.update(force)
		t.release()
	return 0

def do_sysupgrade(options):
	"Upgrade a system like pacman -Su"
	downgrade = (options.sysupgrade > 1)
	t = transaction.init_from_options(handle, options)
	t.sysupgrade(downgrade)
	if len(t.to_add) + len(t.to_remove) == 0:
		print("nothing to do")
		t.release()
		return 0
	else:
		ok = transaction.finalize(t)
		return (0 if ok else 1)

def do_install(pkgs, options):
	"Install a list of packages like pacman -S"
	repos = dict((db.name, db) for db in handle.get_syncdbs())
	if len(pkgs) == 0:
		print("error: no targets specified")
		return 1

	targets = []
	for name in pkgs:
		ok, pkg = find_sync_package(name, repos)
		if not ok:
			print('error:', pkg)
			return 1
		else:
			targets.append(pkg)
	t = transaction.init_from_options(handle, options)
	[t.add_pkg(pkg) for pkg in targets]
	ok = transaction.finalize(t)
	return (0 if ok else 1)

def find_sync_package(pkgname, syncdbs):
	"Finds a package name of the form 'repo/pkgname' or 'pkgname' in a list of DBs"
	if '/' in pkgname:
		repo, pkgname = pkgname.split('/', 1)
		db = syncdbs.get(repo)
		if db is None:
			return False, "repository '%s' does not exist" % repo
		pkg = db.get_pkg(pkgname)
		if pkg is None:
			return False, "package '%s' was not found in repository '%s'" % (pkgname, repo)
		return True, pkg
	else:
		for db in syncdbs.values():
			pkg = db.get_pkg(pkgname)
			if pkg is not None:
				return True, pkg
		return False, "package '%s' was not found" % pkgname

# Query actions

def show_groups(args):
	"Show groups like pacman -Sg"
	for repo in handle.get_syncdbs():
		if len(args.args) == 0:
			# list all available groups
			[print(name) for name, pkgs in repo.grpcache]
		else:
			# only print chosen groups
			for group in args.args:
				grp = repo.read_grp(group)
				if grp is None:
					continue
				else:
					name, pkgs = grp
				if args.quiet:
					[print(pkg.name) for pkg in pkgs]
				else:
					[print(name, pkg.name) for pkg in pkgs]
	return 0

def show_repo(args):
	"Show repository's list of packages like pacman -Sl"
	repos = handle.get_syncdbs()
	if len(args.args) > 0:
		repo_dict = dict((repo.name, repo) for repo in repos)
		try:
			repos = [repo_dict[name] for name in args.args]
		except KeyError as err:
			print("error: repository '%s' was not found" % err.args)
			return 1

	for repo in repos:
		if args.quiet:
			[print(pkg.name) for pkg in repo.pkgcache]
		else:
			[print(repo.name, pkg.name, pkg.version) for pkg in repo.pkgcache]
	return 0

def show_packages(args):
	"Show information about packages like pacman -Si"
	retcode = 0
	if len(args.args) == 0:
		for repo in handle.get_syncdbs():
			for pkg in repo.pkgcache:
				pkginfo.display_pkginfo(pkg, level=args.info, style='sync')
	else:
		repos = dict((db.name, db) for db in handle.get_syncdbs())
		for pkgname in args.args:
			ok, value = find_sync_package(pkgname, repos)
			if ok:
				pkginfo.display_pkginfo(value, level=args.info, style='sync')
			else:
				retcode = 1
				print("error:", value)
	return retcode

def show_search(patterns, options):
	results = []
	for db in handle.get_syncdbs():
		results += db.search(*patterns)
	if len(results) == 0:
		return 1
	for pkg in results:
		if options.quiet:
			print(pkg.name)
		else:
			print("%s/%s %s" % (pkg.db.name, pkg.name, pkg.version))
			print("    " + pkg.desc)
	return 0

def parse_options(rawargs):
	parser = config.make_parser(prog='pycman-sync')
	# Misc actions
	group0 = parser.add_argument_group("Actions (default is installing specified packages)")
	group0.add_argument("-c", "--clean",
			action='count', default=0,
			help='remove old packages from cache directory (-cc for all)')
	group0.add_argument("-u", "--sysupgrade",
			action='count', default=0,
			help='upgrade installed packages (-uu allows downgrade)')
	group0.add_argument("-y", "--refresh",
			action='count', default=0,
			help='download fresh package databases from the server')
	# Installation options
	grp_install = parser.add_argument_group("Install options")
	grp_install.add_argument('-d', '--nodeps',
			action='store_true', default=False,
			help='skip dependency checks')
	grp_install.add_argument('-f', '--force',
			action='store_true', default=False,
			help='force install, overwrite conflicting files')
	grp_install.add_argument('-k', '--dbonly',
			action='store_true', default=False,
			help='only modify database entries, not package files')
	grp_install.add_argument('-w', '--downloadonly',
			action='store_true', default=False,
			help='download packages but do not install/upgrade anything')
	grp_install.add_argument('--asdeps', dest='mode',
			action="store_const",
			const=pyalpm.PKG_REASON_DEPEND)
	grp_install.add_argument('--asexplicit', dest='mode',
			action="store_const",
			const=pyalpm.PKG_REASON_EXPLICIT)
	# Options to query sync databases
	group1 = parser.add_argument_group("Query actions")
	group1.add_argument('-g', '--groups', action='store_true', default=False,
			help='view list of groups, or all members of a package group')
	group1.add_argument('-i', '--info',
			action='count', dest='info', default=0,
			help='view package information')
	group1.add_argument('-l', '--list', action='store_true', default=False,
			help='list the contents of repositories')
	group1.add_argument('-s', '--search', action='store_true', default=False,
			help='search remote repositories for matching strings')
	group1.add_argument('-q', '--quiet',
			action='store_true', dest='quiet', default=False,
			help='show less information for query and search')
	group1.add_argument('args', metavar='arg', nargs='*',
			help='arguments (group names for -g, repo names for -l, '
			'package names for -i)')
	return parser.parse_args(rawargs)

def main(rawargs):
	global handle
	args = parse_options(rawargs)
	handle = config.init_with_config_and_options(args)

	if args.verbose:
		print("sync " + " ".join(rawargs), file=sys.stderr)

	# Refresh databases if necessary
	if args.refresh > 0:
		ret = do_refresh(args)
		if ret != 0:
			return ret

	# If a query action is set
	if args.search:
		return show_search(args.args, args)
	elif args.groups:
		return show_groups(args)
	elif args.info:
		return show_packages(args)
	elif args.list:
		return show_repo(args)
	# If a cleanup is required
	elif args.clean > 0:
		return do_clean(args)
	# If a sysupgrade is required
	elif args.sysupgrade > 0:
		return do_sysupgrade(args)
	# If only a refresh was requested
	elif len(args.args) == 0 and args.refresh > 0:
		return 0
	# Otherwise it's a normal install
	else:
		return do_install(args.args, args)

if __name__ == "__main__":
	ret = main(sys.argv[1:])
	sys.exit(ret)

# vim: set ts=4 sw=4 tw=0 noet:
