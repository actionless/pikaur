""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

from vulture.whitelist_utils import Whitelist


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
