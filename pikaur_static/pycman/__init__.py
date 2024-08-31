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

from . import action_database
from . import action_deptest
from . import action_query
from . import action_remove
from . import action_sync
from . import action_upgrade
from . import action_version

ACTIONS = {
	'db': action_database.main,
	'deptest': action_deptest.main,
	'query': action_query.main,
	'remove': action_remove.main,
	'sync': action_sync.main,
	'upgrade': action_upgrade.main,
	'version': action_version.main
}

def run_action_with_args(action, args):
	if action not in ACTIONS:
		print("Invalid action specified (%s are supported)" % ', '.join(ACTIONS.keys()))
		return 1
	else:
		callback = ACTIONS[action]
		return callback(args)

# vim: set ts=4 sw=4 tw=0 noet:

