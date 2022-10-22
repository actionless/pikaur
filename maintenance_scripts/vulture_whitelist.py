""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

# pylint: disable=protected-access,pointless-statement

from vulture.whitelist_utils import Whitelist  # type: ignore[import]  # pylint: disable=import-error,no-name-in-module


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

whitelist.pikaur_test.setUpClass
whitelist.pikaur_test.foo
whitelist.pikaur_test.bar
whitelist.pikaur_test.baz

whitelist.pikaman.NroffRenderer.strong
whitelist.pikaman.NroffRenderer.emph
whitelist.pikaman.NroffRenderer.softbreak
whitelist.pikaman.NroffRenderer.heading_close
whitelist.pikaman.NroffRenderer.paragraph_open
whitelist.pikaman.NroffRenderer.paragraph_close
whitelist.pikaman.NroffRenderer.image
whitelist.pikaman.NroffRenderer.bullet_list_open
whitelist.pikaman.NroffRenderer.bullet_list_close
whitelist.pikaman.NroffRenderer.list_item_close
whitelist.pikaman.NroffRenderer.link_open
whitelist.pikaman.NroffRenderer.html_block
whitelist.pikaman.NroffRenderer.heading_open
whitelist.pikaman.NroffRenderer.code_inline
whitelist.pikaman.NroffRenderer.list_item_open
whitelist.pikaman.NroffRenderer.fence
whitelist.pikaman.NroffRenderer.link_close
