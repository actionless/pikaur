"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

# pylint: disable=protected-access,pointless-statement

# pylint: disable=import-error,no-name-in-module
from vulture.whitelist_utils import Whitelist  # type: ignore[import-untyped]

whitelist: Whitelist = Whitelist()  # type: ignore[no-any-unimported]

whitelist.__new__
whitelist.Any
whitelist.BinaryIO
whitelist.Final
whitelist.IOStream
whitelist.Iterable
whitelist.MutableMapping
whitelist.NoReturn
whitelist.Pattern
whitelist.Sequence
whitelist.TextIO
whitelist.FrameType
whitelist.TracebackType

whitelist.pikaur.AnyPackage

whitelist.argparse.Action
whitelist.argparse.ArgumentParserWithUnknowns._parse_known_args

whitelist.args.FileType

whitelist.aur.AURPackageInfo.optdepends
whitelist.aur.AURPackageInfo.aur_id
whitelist.aur.AURPackageInfo.packagebaseid
whitelist.aur.AURPackageInfo.maintainer
whitelist.aur.AURPackageInfo.firstsubmitted
whitelist.aur.AURPackageInfo.lastmodified
whitelist.aur.AURPackageInfo.urlpath
whitelist.aur.AURPackageInfo.pkg_license
whitelist.aur.AURPackageInfo.keywords
whitelist.aur.AURPackageInfo.git_url
whitelist.aur.AURPackageInfo.web_url
whitelist.aur.AURPackageInfo.submitter
whitelist.aur.AURPackageInfo.comaintainers

whitelist.build.PackageBuild._get_deps.deps_destination

whitelist.config.DeprecatedConfigValue.option
whitelist.config.ConfigValueType.data_type
whitelist.config.ConfigValueType.deprecated
whitelist.config.ConfigValueType.migrated

whitelist.core.SpawnArgs
whitelist.core.SudoLoopResultT

whitelist.i18n.EXTRA_ERROR_MESSAGES

whitelist.main.socket.socket
whitelist.main.OutputEncodingWrapper.original_stdout
whitelist.main.OutputEncodingWrapper.original_stderr

whitelist.makepkg_config.FallbackValueT

whitelist.news.Element
whitelist.news.MLStripper.convert_charrefs
whitelist.news.MLStripper.handle_data
whitelist.news.MLStripper.handle_endtag
whitelist.news.MLStripper.handle_starttag
whitelist.news.MLStripper.strict

whitelist.print_department.InstallInfoT

whitelist.pprint.DefaultNamedArg

whitelist.search_cli.SamePackageTypeT

whitelist.pikaur_test.helpers.DefaultArg
whitelist.pikaur_test.setUpClass
whitelist.pikaur_test.tearDownClass
whitelist.pikaur_test.TestResult
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
whitelist.pikaman.NroffRenderer.ordered_list_open
whitelist.pikaman.NroffRenderer.ordered_list_close
whitelist.pikaman.NroffRenderer.list_item_close
whitelist.pikaman.NroffRenderer.link_open
whitelist.pikaman.NroffRenderer.html_block
whitelist.pikaman.NroffRenderer.heading_open
whitelist.pikaman.NroffRenderer.code_inline
whitelist.pikaman.NroffRenderer.list_item_open
whitelist.pikaman.NroffRenderer.fence
whitelist.pikaman.NroffRenderer.link_close
