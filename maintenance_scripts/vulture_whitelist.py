"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

# pylint: disable=protected-access,pointless-statement

# pylint: disable=import-error,no-name-in-module
from vulture.whitelist_utils import Whitelist  # type: ignore[import-untyped]

###############################################################################
#
# vulture  --make-whitelist  pikaur_static/*.py
#
###############################################################################

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

whitelist.argparse_extras.ArgumentParserWithUnknowns._parse_known_args

whitelist.args.FileType
whitelist.args.PikaurArgs.pacman_conf_path

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

whitelist.i18n.EXTRA_ERROR_MESSAGES

whitelist.main.OutputEncodingWrapper.original_stdout
whitelist.main.OutputEncodingWrapper.original_stderr

whitelist.news.MLStripper.convert_charrefs
whitelist.news.MLStripper.handle_data
whitelist.news.MLStripper.handle_endtag
whitelist.news.MLStripper.handle_starttag
whitelist.news.MLStripper.strict

whitelist.pikaur_static.pacman_fallback._.compute_requiredby
whitelist.pikaur_static.pacman_fallback._.compute_optionalfor
whitelist.pikaur_static.pacman_fallback.PacmanPackageInfoType
whitelist.pikaur_static.pacman_fallback.PackageDBCommonType
whitelist.pikaur_static.pyalpm._.register_syncdb
whitelist.pikaur_static.pyalpm._.get_syncdbs
whitelist.pikaur_static.pyalpm._.get_localdb
whitelist.pikaur_static.pyalpm.LOG_WARNING
whitelist.pikaur_static.pyalpm.LOG_ERROR
whitelist.pikaur_static.pyalpm.vercmp
whitelist.pikaur_static.pypyalpm._.get_pkg
whitelist.pikaur_static.pypyalpm._.compute_requiredby
whitelist.pikaur_static.pypyalpm._.compute_optionalfor
whitelist.pikaur_static.pypyalpm._.search
whitelist.pikaur_static.pypyalpm._.all
whitelist.pikaur_static.pypyalpm.has_scriptlet
whitelist.pikaur_static.pypyalpm.base64_sig
whitelist.pikaur_static.pypyalpm.NOT_FOUND_ATOM
whitelist.pikaur_static.pypyalpm.validation
whitelist.pikaur_static.pypyalpm.url
whitelist.pikaur_static.pypyalpm.size
whitelist.pikaur_static.pypyalpm.sha256sum
whitelist.pikaur_static.pypyalpm.replaces
whitelist.pikaur_static.pypyalpm.packager
whitelist.pikaur_static.pypyalpm.md5sum
whitelist.pikaur_static.pypyalpm.licenses
whitelist.pikaur_static.pypyalpm.isize
whitelist.pikaur_static.pypyalpm.installdate
whitelist.pikaur_static.pypyalpm.groups
whitelist.pikaur_static.pypyalpm.filename
whitelist.pikaur_static.pypyalpm.desc
whitelist.pikaur_static.pypyalpm.data
whitelist.pikaur_static.pypyalpm.conflicts
whitelist.pikaur_static.pypyalpm.builddate
whitelist.pikaur_static.pypyalpm.base
whitelist.pikaur_static.pypyalpm.arch

whitelist.pikaur_test.helpers.DefaultArg
whitelist.pikaur_test.setUpClass
whitelist.pikaur_test.tearDownClass
whitelist.pikaur_test.TestResult
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
