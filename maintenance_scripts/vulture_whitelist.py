""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

# pylint: disable=invalid-name,protected-access,pointless-statement

from vulture.whitelist_utils import Whitelist  # pylint: disable=import-error,no-name-in-module


whitelist = Whitelist()

whitelist.build.PackageBuild._get_deps.deps_destination

whitelist.news.MLStripper.strict
whitelist.news.MLStripper.convert_charrefs
whitelist.news.MLStripper.handle_data

whitelist.aur.AURPackageInfo.optdepends
whitelist.aur.AURPackageInfo.id
whitelist.aur.AURPackageInfo.packagebaseid
whitelist.aur.AURPackageInfo.maintainer
whitelist.aur.AURPackageInfo.firstsubmitted
whitelist.aur.AURPackageInfo.lastmodified
whitelist.aur.AURPackageInfo.urlpath
whitelist.aur.AURPackageInfo.license
whitelist.aur.AURPackageInfo.keywords

whitelist.argparse.ArgumentParserWithUnknowns._parse_known_args
