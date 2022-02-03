""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

# pylint: disable=protected-access,pointless-statement

from vulture.whitelist_utils import Whitelist  # pylint: disable=import-error,no-name-in-module


whitelist = Whitelist()

whitelist.argparse.ArgumentParserWithUnknowns._parse_known_args

whitelist.aur.AURPackageInfo.optdepends
whitelist.aur.AURPackageInfo.id
whitelist.aur.AURPackageInfo.packagebaseid
whitelist.aur.AURPackageInfo.maintainer
whitelist.aur.AURPackageInfo.firstsubmitted
whitelist.aur.AURPackageInfo.lastmodified
whitelist.aur.AURPackageInfo.urlpath
whitelist.aur.AURPackageInfo.license
whitelist.aur.AURPackageInfo.keywords
whitelist.aur.AURPackageInfo.git_url

whitelist.build.PackageBuild._get_deps.deps_destination

whitelist.main.socket.socket

whitelist.news.MLStripper.convert_charrefs
whitelist.news.MLStripper.handle_data
whitelist.news.MLStripper.strict

whitelist.test_unit.foo
whitelist.test_unit.bar
