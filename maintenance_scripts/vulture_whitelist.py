""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

# pylint: disable=invalid-name,protected-access,pointless-statement

from vulture.whitelist_utils import Whitelist  # pylint: disable=import-error,no-name-in-module


whitelist = Whitelist()

whitelist.argparse.ArgumentParserWithUnknowns._parse_known_args

whitelist.args.CachedArgs.args.color

whitelist.aur.AURPackageInfo.firstsubmitted
whitelist.aur.AURPackageInfo.id
whitelist.aur.AURPackageInfo.keywords
whitelist.aur.AURPackageInfo.lastmodified
whitelist.aur.AURPackageInfo.license
whitelist.aur.AURPackageInfo.maintainer
whitelist.aur.AURPackageInfo.optdepends
whitelist.aur.AURPackageInfo.packagebaseid
whitelist.aur.AURPackageInfo.urlpath

whitelist.build.PackageBuild._get_deps.deps_destination

whitelist.config.PikaurConfig._config

whitelist.news.MLStripper.convert_charrefs
whitelist.news.MLStripper.handle_data
whitelist.news.MLStripper.strict

whitelist.pikspect.Pikspect.get_output_bytes

# test:
whitelist.helpers.InterceptSysOutput.out_file.isatty
whitelist.helpers.InterceptSysOutput.err_file.isatty
