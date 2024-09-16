#!/usr/bin/env python3
#
# pycman - A Python implementation of Pacman
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
pycman configuration handling

This module handles pacman.conf files as well as pycman options that
are common to all action modes.
"""

import os
import glob
import sys
import argparse
import collections
import warnings

import pyalpm

class InvalidSyntax(Warning):
	def __init__(self, filename, problem, arg):
		self.filename = filename
		self.problem = problem
		self.arg = arg

	def __str__(self):
		return "unable to parse %s, %s: %r" % (self.filename, self.problem, self.arg)

# Options that may occur several times in a section. Their values should be
# accumulated in a list.
LIST_OPTIONS = (
	'CacheDir',
	'HookDir',
	'HoldPkg',
	'SyncFirst',
	'IgnoreGroup',
	'IgnorePkg',
	'NoExtract',
	'NoUpgrade',
	'Server'
)

SINGLE_OPTIONS = (
	'RootDir',
	'DBPath',
	'GPGDir',
	'LogFile',
	'Architecture',
	'XferCommand',
	'CacheServer',
	'CleanMethod',
	'SigLevel',
	'LocalFileSigLevel',
	'RemoteFileSigLevel',
	'ParallelDownloads',
	'DownloadUser',
)

BOOLEAN_OPTIONS = (
	'UseSyslog',
	'ShowSize',
	'CheckSpace',
	'VerbosePkgLists',
	'ILoveCandy',
	'Color',
	'DisableDownloadTimeout',
	'NoProgressBar',
	'DisableSandbox',
)


class PacmanConfEnumeratorSession():

	def __init__(self, path):
		self.path = path
		self.file_descriptors = []

	def _enumerator(self):
		filestack = []
		current_section = None
		new_fd = open(self.path, 'rb')
		self.file_descriptors.append(new_fd)
		filestack.append(new_fd)
		while len(filestack) > 0:
			f = filestack[-1]
			line = f.readline()
			line = line.decode('utf-8')
			if len(line) == 0:
				# end of file
				filestack.pop()
				continue

			line = line.strip()
			if len(line) == 0: continue
			if line[0] == '#':
				continue
			if line[0] == '[' and line[-1] == ']':
				current_section = line[1:-1]
				continue
			# read key, value
			key, equal, value = [x.strip() for x in line.partition('=')]

			if current_section is None and key != 'Include':
				raise InvalidSyntax(f.name, 'statement outside of a section', line)

			# include files
			if equal == '=' and key == 'Include':
				new_fds = [open(f, 'rb') for f in glob.glob(value)]
				filestack.extend(new_fds)
				self.file_descriptors.extend(new_fds)
				continue
			if current_section != 'options':
				# repos only have the Server, SigLevel, Usage options
				if key in ('Server', 'SigLevel', 'Usage', 'CacheServer') and equal == '=':
					yield (current_section, key, value)
				else:
					raise InvalidSyntax(f.name, 'invalid key for repository configuration', line)
				continue
			if equal == '=':
				if key in LIST_OPTIONS:
					for val in value.split():
						yield (current_section, key, val)
				elif key in SINGLE_OPTIONS:
					yield (current_section, key, value)
				else:
					warnings.warn(InvalidSyntax(f.name, 'unrecognized option', key))
			else:
				if key in BOOLEAN_OPTIONS:
					yield (current_section, key, True)
				else:
					warnings.warn(InvalidSyntax(f.name, 'unrecognized option', key))

	def __enter__(self):
		return self._enumerator

	def __exit__(self, *exc_details):
		for fd in self.file_descriptors:
			fd.close()


_logmask = pyalpm.LOG_ERROR | pyalpm.LOG_WARNING

def cb_log(level, line):
	if not (level & _logmask):
		return
	if level & pyalpm.LOG_ERROR:
		line = "ERROR: " + line
	elif level & pyalpm.LOG_WARNING:
		line = "WARNING: " + line
	elif level & pyalpm.LOG_DEBUG:
		line = "DEBUG: " + line
	elif level & pyalpm.LOG_FUNCTION:
		line = "FUNC: " + line
	sys.stderr.write(line)

class PacmanConfig(object):
	def __init__(self, conf=None, options=None):
		self.options = {}
		self.repos = collections.OrderedDict()
		self.options["RootDir"] = "/"
		self.options["DBPath"] = "/var/lib/pacman"
		self.options["GPGDir"] = "/etc/pacman.d/gnupg/"
		self.options["LogFile"] = "/var/log/pacman.log"
		self.options["Architecture"] = os.uname()[-1]
		if conf is not None:
			self.load_from_file(conf)
		if options is not None:
			self.load_from_options(options)

	def load_from_file(self, filename):
		with PacmanConfEnumeratorSession(filename) as pacman_conf_enumerator:
			for section, key, value in pacman_conf_enumerator():
				if section == 'options':
					if key == 'Architecture' and value == 'auto':
						continue
					if key in LIST_OPTIONS:
						self.options.setdefault(key, []).append(value)
					else:
						self.options[key] = value
				else:
					servers = self.repos.setdefault(section, [])
					if key == 'Server':
						servers.append(value)
		if "CacheDir" not in self.options:
			self.options["CacheDir"] = ["/var/cache/pacman/pkg"]

	def load_from_options(self, options):
		global _logmask
		if options.root is not None:
			self.options["RootDir"] = options.root
		if options.dbpath is not None:
			self.options["DBPath"] = options.dbpath
		if options.gpgdir is not None:
			self.options["GPGDir"] = options.gpgdir
		if options.arch is not None:
			self.options["Architecture"] = options.arch
		if options.logfile is not None:
			self.options["LogFile"] = options.logfile
		if options.cachedir is not None:
			self.options["CacheDir"] = [options.cachedir]
		if options.debug:
			_logmask = 0xffff

	def apply(self, h):
		# File paths
		h.logfile = self.options["LogFile"]
		h.gpgdir = self.options["GPGDir"]
		# Lists
		arch = self.options["Architecture"]
		if isinstance(arch, str):
			arch = [arch]
		h.arch = arch
		h.cachedirs = self.options["CacheDir"]
		if "NoUpgrade" in self.options:
			h.noupgrades = self.options["NoUpgrade"]
		if "NoExtract" in self.options:
			h.noextracts = self.options["NoExtract"]
		if "IgnorePkg" in self.options:
			h.ignorepkgs = self.options["IgnorePkg"]
		if "IgnoreGroup" in self.options:
			h.ignoregrps = self.options["IgnoreGroup"]

		h.logcb = cb_log

		# set sync databases
		for repo, servers in self.repos.items():
			db = h.register_syncdb(repo, 0)
			db_servers = []
			for rawurl in servers:
				url = rawurl.replace("$repo", repo)
				url = url.replace("$arch", self.options["Architecture"])
				db_servers.append(url)
			db.servers = db_servers

	def initialize_alpm(self):
		h = pyalpm.Handle(self.options["RootDir"], self.options["DBPath"])
		self.apply(h)
		return h

	def __str__(self):
		return("PacmanConfig(options=%s, repos=%s)" % (str(self.options), str(self.repos)))

def make_parser(*args, **kwargs):
	parser = argparse.ArgumentParser(*args, **kwargs)
	common = parser.add_argument_group('Common options')
	common.add_argument('-b', '--dbpath', metavar='<path>',
			action='store', dest='dbpath', type=str,
			help='set an alternate database location')
	common.add_argument('-r', '--root', metavar='<path>',
			action='store', dest='root', type=str,
			help='set an alternate installation root')
	common.add_argument('-v', '--verbose',
			action='store_true', dest='verbose', default=False,
			help='be verbose')
	common.add_argument('--arch', metavar='<arch>',
			action='store', dest='arch', type=str,
			help='set an alternate architecture')
	common.add_argument('--config', metavar='<file>',
			action='store', dest='config', type=str,
			help='set an alternate configuration file')
	common.add_argument('--debug',
			action='store_true', dest='debug',
			help='display debug messages')
	common.add_argument('--logfile', metavar='<file>',
			action='store', dest='logfile', type=str,
			help='set an alternate log file')
	common.add_argument('--gpgdir', metavar='<dir>',
			action='store', dest='gpgdir', type=str,
			help='set an alternate log file')
	common.add_argument('--cachedir', metavar='<dir>',
			action='store', dest='cachedir', type=str,
			help='set an alternate cche location')
	return parser

def init_with_config(configpath):
	"Reads configuration from given path and apply it to libalpm"
	config = PacmanConfig(conf=configpath)
	return config.initialize_alpm()

def init_with_config_and_options(options):
	"Reads configuration from file and commandline options, and apply it to libalpm"
	# read config file
	if options.config is not None:
		config_file = options.config
	else:
		config_file = "/etc/pacman.conf"

	conf = PacmanConfig(conf=config_file, options=options)
	return conf.initialize_alpm()

# vim: set ts=4 sw=4 tw=0 noet:
