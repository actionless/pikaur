"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
import functools
import operator
from itertools import chain
from multiprocessing.pool import ThreadPool
from typing import TYPE_CHECKING, cast

from .alpm import OFFICIAL_REPOS, PacmanConfig
from .args import parse_args, reconstruct_args
from .aur import find_aur_packages, find_aur_provided_deps, strip_aur_repo_name
from .aur_deps import find_aur_deps, find_repo_deps_of_aur_pkgs
from .exceptions import DependencyError, DependencyVersionMismatchError, SysExit
from .i18n import translate
from .logging_extras import create_logger
from .pacman import (
    PackageDB,
    find_sysupgrade_packages,
    get_ignored_pkgnames_from_patterns,
    get_pacman_command,
    strip_repo_name,
)
from .pikaprint import print_error, print_stderr, print_stdout
from .pikatypes import (
    AURInstallInfo,
    AURPackageInfo,
    ComparableType,
    PackageSource,
    RepoInstallInfo,
)
from .print_department import print_ignored_package, print_not_found_packages
from .prompt import ask_to_continue
from .replacements import find_replacements
from .srcinfo import SrcInfo
from .updates import find_aur_updates, print_upgradeable
from .version import VersionMatcher

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .args import PikaurArgs
    from .pacman import PacmanPrint
    from .pikatypes import InstallInfo

logger = create_logger("install_info_fetcher")


class InstallInfoFetcher(ComparableType):  # noqa: PLR0904

    repo_packages_install_info: list[RepoInstallInfo]
    new_repo_deps_install_info: list[RepoInstallInfo]
    thirdparty_repo_packages_install_info: list[RepoInstallInfo]
    new_thirdparty_repo_deps_install_info: list[RepoInstallInfo]
    repo_replacements_install_info: list[RepoInstallInfo]
    thirdparty_repo_replacements_install_info: list[RepoInstallInfo]
    aur_updates_install_info: list[AURInstallInfo]
    aur_deps_install_info: list[AURInstallInfo]
    _all_aur_updates_raw: list[AURInstallInfo]

    args: "PikaurArgs"
    aur_deps_relations: dict[str, list[str]]
    replacements: dict[str, list[str]]
    skip_checkdeps_for_pkgnames: list[str]

    __ignore_in_eq__ = ("args", )

    def __init__(
            self,
            install_package_names: list[str],
            not_found_repo_pkgs_names: list[str],
            manually_excluded_packages_names: list[str],
            pkgbuilds_packagelists: dict[str, list[str]],
            skip_checkdeps_for_pkgnames: list[str] | None = None,
    ) -> None:
        logger.debug(
            """
Gonna fetch install info for:
    install_package_names={}
    not_found_repo_pkgs_names={}
    pkgbuilds_packagelists={}
    manually_excluded_packages_names={}
    skip_checkdeps_for_pkgnames={}
""",
            install_package_names,
            not_found_repo_pkgs_names,
            pkgbuilds_packagelists,
            manually_excluded_packages_names,
            skip_checkdeps_for_pkgnames,
        )
        self.args = parse_args()
        self.install_package_names = install_package_names
        self.not_found_repo_pkgs_names = not_found_repo_pkgs_names
        self.manually_excluded_packages_names = manually_excluded_packages_names
        self.pkgbuilds_packagelists = pkgbuilds_packagelists
        self.replacements = find_replacements() if self.args.sysupgrade else {}
        self.skip_checkdeps_for_pkgnames = skip_checkdeps_for_pkgnames or []

        self.get_all_packages_info()
        if self.args.sysupgrade:
            # print ignored package updates:
            print_upgradeable(
                ignored_only=True,
                aur_install_infos=self._all_aur_updates_raw,
            )

    def package_is_ignored(self, package_name: str) -> bool:
        return bool(
            package_name in get_ignored_pkgnames_from_patterns(
                [package_name],
                self.args.ignore + PacmanConfig().options.get("IgnorePkg", []),
            )
            and not (
                package_name in self.install_package_names
                or package_name in self.not_found_repo_pkgs_names),
        )

    def exclude_ignored_packages(
            self,
            package_names: list[str],
            *,
            print_packages: bool = True,
    ) -> None:
        ignored_packages = []
        for pkg_name in package_names.copy():
            if self.package_is_ignored(pkg_name):
                package_names.remove(pkg_name)
                ignored_packages.append(pkg_name)
        if print_packages:
            for package_name in ignored_packages:
                print_ignored_package(package_name=package_name)

    @property
    def aur_packages_names(self) -> list[str]:
        return [
            pkg_info.name for pkg_info in self.aur_updates_install_info
        ]

    @property
    def aur_deps_names(self) -> list[str]:
        _aur_deps_names: list[str] = []
        for deps in self.aur_deps_relations.values():
            _aur_deps_names += deps
        return list(set(_aur_deps_names))

    @property
    def aur_install_info_containers(self) -> "Sequence[list[AURInstallInfo]]":
        return (
            self.aur_updates_install_info,
            self.aur_deps_install_info,
        )

    @property
    def repo_install_info_containers(self) -> "Sequence[list[RepoInstallInfo]]":
        return (
            self.repo_packages_install_info,
            self.new_repo_deps_install_info,
            self.repo_replacements_install_info,
            self.thirdparty_repo_packages_install_info,
            self.new_thirdparty_repo_deps_install_info,
            self.thirdparty_repo_replacements_install_info,
        )

    @property
    def all_install_info_containers(
            self,
    ) -> "Sequence[list[RepoInstallInfo] | list[AURInstallInfo]]":
        return (
            *self.repo_install_info_containers,
            *self.aur_install_info_containers,
        )

    @property
    def repo_install_info(self) -> list[RepoInstallInfo]:
        return [
            info
            for infos in self.repo_install_info_containers
            for info in infos
        ]

    @property
    def aur_install_info(self) -> list[AURInstallInfo]:
        return [
            info
            for infos in self.aur_install_info_containers
            for info in infos
        ]

    @property
    def all_install_info(self) -> "Sequence[RepoInstallInfo | AURInstallInfo]":
        return list(self.repo_install_info) + list(self.aur_install_info)

    def discard_package(
            self, canceled_pkg_name: str, already_discarded: list[str] | None = None,
    ) -> list[str]:
        logger.debug("discarding {}", canceled_pkg_name)
        for container in self.all_install_info_containers:
            for info in container[:]:
                if info.name == canceled_pkg_name:
                    container.remove(info)  # type: ignore[arg-type]

        already_discarded = (already_discarded or []) + [canceled_pkg_name]
        for aur_pkg_name, aur_deps in list(self.aur_deps_relations.items())[:]:
            if canceled_pkg_name == aur_pkg_name:
                logger.debug("{} have deps: {}", aur_pkg_name, aur_deps)
                for pkg_name in [*aur_deps, aur_pkg_name]:
                    if pkg_name not in already_discarded:
                        already_discarded += self.discard_package(pkg_name, already_discarded)
                if aur_pkg_name in self.aur_deps_relations:
                    del self.aur_deps_relations[aur_pkg_name]
        return list(set(already_discarded))

    def get_all_packages_info(self) -> None:
        """
        Retrieve info (`InstallInfo` objects) of packages
        which are going to be installed/upgraded and their dependencies
        """
        self.exclude_ignored_packages(self.install_package_names)

        self.repo_packages_install_info = []
        self.new_repo_deps_install_info = []
        self.thirdparty_repo_packages_install_info = []
        self.new_thirdparty_repo_deps_install_info = []
        self.repo_replacements_install_info = []
        self.thirdparty_repo_replacements_install_info = []
        self.aur_updates_install_info = []
        self.aur_deps_install_info = []
        self._all_aur_updates_raw = []

        # retrieve InstallInfo objects for repo packages to be installed
        # and their upgrades if --sysupgrade was passed
        if not self.args.aur:
            logger.debug("Gonna get repo pkgs install info...")
            self.get_repo_pkgs_info()

        # retrieve InstallInfo objects for AUR packages to be installed
        # and their upgrades if --sysupgrade was passed
        if not self.args.repo:
            self.get_aur_pkgs_info(self.not_found_repo_pkgs_names)
        if self.pkgbuilds_packagelists:
            self.get_info_from_pkgbuilds()

        # try to find AUR deps for AUR packages
        # if some exception wasn't handled inside -- just write message and exit
        self.get_aur_deps_info()

        # find repo deps for AUR packages
        self.get_repo_deps_info()

        self.mark_dependent()

    # pylint: disable=too-many-statements,too-many-locals,too-many-branches
    def _get_repo_pkgs_info(
            self, pkg_lines: list[str], extra_args: list[str] | None = None,
    ) -> list[RepoInstallInfo]:
        if not pkg_lines:
            return []

        extra_args = extra_args or []
        all_repo_pkgs = PackageDB.get_repo_dict()
        all_local_pkgs = PackageDB.get_local_dict()

        # pacman print-info flag conflicts with some normal --sync options:
        pacman_args = [
            *get_pacman_command(ignore_args=[
                "overwrite",
            ]),
            "--sync",
            *reconstruct_args(
                self.args, ignore_args=[
                    "sync",
                    "ignore",
                    "sysupgrade",
                    "refresh",
                    "needed",
                    "verbose",
                    "overwrite",
                    "search",
                ],
            ),
            *extra_args,
        ]

        def _get_pkg_install_infos(results: "list[PacmanPrint]") -> list[RepoInstallInfo]:
            install_infos = []
            for pkg_print in results:
                pkg = all_repo_pkgs[pkg_print.full_name]
                local_pkg = all_local_pkgs.get(pkg.name)
                install_info = RepoInstallInfo(
                    name=pkg.name,
                    current_version=local_pkg.version if local_pkg else "",
                    new_version=pkg.version,
                    description=pkg.desc,
                    repository=pkg.db.name,
                    package=pkg,
                )

                groups = install_info.package.groups
                members_of = [
                    gr for gr in groups
                    if gr in self.install_package_names
                ]
                if members_of:
                    install_info.members_of = members_of

                install_infos.append(install_info)
            return install_infos

        try:
            logger.debug("Checking if '{}' is installable:", pkg_lines)
            composed_result = PackageDB.get_print_format_output(
                pacman_args + [
                    pkg
                    for pkg_line in pkg_lines
                    for pkg in pkg_line.split(",")
                ],
            )
        except DependencyError:
            logger.debug("Check failed - gonna check it separately:")
            composed_result = []
        if composed_result:
            logger.debug("Check passed - gonna get install infos:")
            return _get_pkg_install_infos(composed_result)

        all_results = {}
        with ThreadPool() as pool:
            pkg_exists_requests = {}
            for pkg_name in pkg_lines.copy():
                logger.debug("Checking if '{}' exists in the repo:", pkg_name)
                pkg_exists_requests[pkg_name] = pool.apply_async(
                    PackageDB.get_print_format_output,
                    (pacman_args + pkg_name.split(","), ),
                    {"check_deps": False, "package_only": True},
                )
            pool.close()
            pool.join()
            for pkg_name, request in pkg_exists_requests.items():
                try:
                    all_results[pkg_name] = request.get()
                    logger.debug("  '{}' is found in the repo.", pkg_name)
                except DependencyError:
                    all_results[pkg_name] = []
                    logger.debug("  '{}' is NOT found in the repo.", pkg_name)

        with ThreadPool() as pool:
            pkg_installable_requests = {}
            for pkg_name, results in all_results.items():
                if not results:
                    continue
                logger.debug("Checking if '{}' is installable:", pkg_name)
                pkg_installable_requests[pkg_name] = pool.apply_async(
                    PackageDB.get_print_format_output,
                    (pacman_args + pkg_name.split(","), ),
                )
            pool.close()
            pool.join()
            for pkg_name, request in pkg_installable_requests.items():
                try:
                    request.get()
                    logger.debug("  '{}' is installable.", pkg_name)
                except DependencyError as exc:
                    print_error(f"'{pkg_name}' is NOT installable.")
                    print_stderr(str(exc))
                    if not ask_to_continue():
                        raise SysExit(125) from exc

        logger.debug("Check partially passed - gonna get install infos:")
        pkg_install_infos: list[RepoInstallInfo] = []
        for pkg_name, results in all_results.items():
            if not results:
                self.not_found_repo_pkgs_names.append(pkg_name)
                if pkg_name in self.install_package_names:
                    self.install_package_names.remove(pkg_name)
            else:
                pkg_install_infos += _get_pkg_install_infos(results)
        return pkg_install_infos

    def get_upgradeable_repo_pkgs_info(self) -> list[RepoInstallInfo]:
        """
        Unlike `pikaur.updates.find_repo_upgradeable`
        it find which repo packages are actually going to be upgraded
        (like `pacman -Su` dry-run).
        """
        if not self.args.sysupgrade:
            return []
        all_local_pkgs = PackageDB.get_local_dict()
        pkg_install_infos = []
        for pkg in find_sysupgrade_packages(
                ignore_pkgs=self.manually_excluded_packages_names,
                install_pkgs=self.install_package_names,
        ):
            local_pkg = all_local_pkgs.get(pkg.name)
            install_info = RepoInstallInfo(
                name=pkg.name,
                current_version=local_pkg.version if local_pkg else "",
                new_version=pkg.version,
                description=pkg.desc,
                repository=pkg.db.name,
                package=pkg,
            )
            pkg_install_infos.append(install_info)
        return pkg_install_infos

    def package_is_manually_excluded(self, pkg_name: str) -> bool:
        return (
            pkg_name in self.manually_excluded_packages_names or
            strip_repo_name(pkg_name) in self.manually_excluded_packages_names or
            pkg_name in [
                strip_repo_name(exc_name) for exc_name in self.manually_excluded_packages_names
            ]
        )

    def get_repo_pkgs_info(self) -> None:
        for pkg_update in (
                self._get_repo_pkgs_info(pkg_lines=self.install_package_names) +
                self.get_upgradeable_repo_pkgs_info()
        ):
            if pkg_update in self.repo_install_info:
                continue

            pkg_name = pkg_update.name
            if (
                    self.package_is_manually_excluded(pkg_name)
            ) or (
                self.package_is_ignored(pkg_name)
            ):
                continue

            if (
                    (not pkg_update.current_version)
                    and (pkg_name not in self.install_package_names)
                    and (not pkg_update.provided_by)
                    and (not pkg_update.members_of)
            ):
                if pkg_name in self.replacements:
                    pkg_update.replaces = self.replacements[pkg_name]
                    if pkg_update.repository in OFFICIAL_REPOS:
                        self.repo_replacements_install_info.append(pkg_update)
                    else:
                        self.thirdparty_repo_replacements_install_info.append(pkg_update)
                    continue
                if pkg_update.repository in OFFICIAL_REPOS:
                    self.new_repo_deps_install_info.append(pkg_update)
                else:
                    self.new_thirdparty_repo_deps_install_info.append(pkg_update)
                continue
            if pkg_update.repository in OFFICIAL_REPOS:
                self.repo_packages_install_info.append(pkg_update)
            else:
                self.thirdparty_repo_packages_install_info.append(pkg_update)

    def get_repo_deps_info(self) -> None:
        all_aur_pkgs: list[AURPackageInfo] = [
            pkg_info.package
            for pkg_info in self.aur_updates_install_info + self.aur_deps_install_info
        ]
        new_dep_version_matchers = find_repo_deps_of_aur_pkgs(
            all_aur_pkgs, skip_checkdeps_for_pkgnames=self.skip_checkdeps_for_pkgnames,
        )
        new_dep_lines = [
            vm.line for vm in new_dep_version_matchers
        ]

        for dep_install_info in self._get_repo_pkgs_info(
                pkg_lines=new_dep_lines, extra_args=["--needed"],
        ):
            if dep_install_info.name in [
                    install_info.name for install_info in
                    (self.new_repo_deps_install_info + self.new_thirdparty_repo_deps_install_info)
            ]:
                continue
            if dep_install_info.repository in OFFICIAL_REPOS:
                self.new_repo_deps_install_info.append(dep_install_info)
            else:
                self.new_thirdparty_repo_deps_install_info.append(dep_install_info)

    def get_aur_pkgs_info(  # pylint: disable=too-many-branches
            self, aur_packages_versionmatchers: list[str],
    ) -> None:
        aur_packages_names_to_versions = {
            strip_aur_repo_name(version_matcher.pkg_name): version_matcher
            for version_matcher in [VersionMatcher(name) for name in aur_packages_versionmatchers]
        }
        logger.debug(
            "gonna get AUR pkgs install info for:\n"
            "    aur_packages_versionmatchers={}\n"
            "    self.aur_updates_install_info={}\n"
            "    aur_packages_names_to_versions={}",
            aur_packages_versionmatchers,
            self.aur_updates_install_info,
            aur_packages_names_to_versions,
        )
        local_pkgs = PackageDB.get_local_dict()
        aur_pkg_list, not_found_aur_pkgs = find_aur_packages(
            list(aur_packages_names_to_versions.keys()),
        )
        logger.debug(
            "found AUR pkgs:\n"
            "    aur_pkg_list={}\n"
            "not found AUR pkgs:\n"
            "    not_found_aur_pkgs={}",
            aur_pkg_list,
            not_found_aur_pkgs,
        )
        aur_pkgs = {}
        for aur_pkg in aur_pkg_list:
            if aur_packages_names_to_versions[aur_pkg.name](aur_pkg.version):
                aur_pkgs[aur_pkg.name] = aur_pkg
            else:
                not_found_aur_pkgs.append(aur_packages_names_to_versions[aur_pkg.name].line)
        if not_found_aur_pkgs:
            logger.debug("error code: 3fh7n834fh7n")
            print_not_found_packages(sorted(not_found_aur_pkgs))
            raise SysExit(6)
        aur_updates_install_info_by_name: dict[str, AURInstallInfo] = {}
        if self.args.sysupgrade:
            self._all_aur_updates_raw, not_found_aur_pkgs = find_aur_updates()
            self.exclude_ignored_packages(not_found_aur_pkgs, print_packages=False)
            if not_found_aur_pkgs:
                logger.debug("error code: 789sdfgh789sd6")
                print_not_found_packages(sorted(not_found_aur_pkgs))
            aur_updates_install_info_by_name = {
                upd.name: upd for upd in self._all_aur_updates_raw
            }
        for pkg_name, aur_pkg in aur_pkgs.items():
            if pkg_name in aur_updates_install_info_by_name:
                continue
            local_pkg = local_pkgs.get(pkg_name)
            aur_updates_install_info_by_name[pkg_name] = AURInstallInfo(
                name=pkg_name,
                current_version=local_pkg.version if local_pkg else " ",
                new_version=aur_pkg.version,
                description=aur_pkg.desc,
                maintainer=aur_pkg.maintainer,
                package=aur_pkg,
            )
        for pkg_name in list(aur_updates_install_info_by_name.keys())[:]:
            if pkg_name not in aur_updates_install_info_by_name:
                continue
            if (
                    self.package_is_manually_excluded(pkg_name)
            ) or (
                self.package_is_ignored(pkg_name)
            ):
                del aur_updates_install_info_by_name[pkg_name]
            else:
                for pkg_list in self.pkgbuilds_packagelists.values():
                    if pkg_name in pkg_list:
                        del aur_updates_install_info_by_name[pkg_name]
        self.aur_updates_install_info += list(aur_updates_install_info_by_name.values())
        logger.debug("got AUR pkgs install info: {}", self.aur_updates_install_info)

    def get_info_from_pkgbuilds(self) -> None:
        logger.debug(
            "<< gonna get install info from PKGBUILDs: {}...", self.aur_updates_install_info,
        )
        aur_updates_install_info_by_name: dict[str, AURInstallInfo] = {}
        local_pkgs = PackageDB.get_local_dict()
        for path, pkg_names in self.pkgbuilds_packagelists.items():
            found_pkg_names = pkg_names
            common_srcinfo = SrcInfo(pkgbuild_path=path)
            common_srcinfo.regenerate()
            if not found_pkg_names:
                found_pkg_names = common_srcinfo.pkgnames
            logger.debug("  1 {} {} {}", path, pkg_names, found_pkg_names)
            for pkg_name in found_pkg_names:
                if pkg_name in self.manually_excluded_packages_names:
                    continue
                srcinfo = SrcInfo(pkgbuild_path=path, package_name=pkg_name)
                aur_pkg = AURPackageInfo.from_srcinfo(srcinfo)
                logger.debug("  2 {} {} {}", pkg_name, aur_pkg, aur_pkg.packagebase)
                if pkg_name in aur_updates_install_info_by_name:
                    raise RuntimeError(translate(f"{pkg_name} already added to the list"))
                local_pkg = local_pkgs.get(pkg_name)
                info = AURInstallInfo(
                    name=pkg_name,
                    current_version=local_pkg.version if local_pkg else " ",
                    new_version=aur_pkg.version,
                    description=aur_pkg.desc,
                    maintainer="local user",
                    package=aur_pkg,
                    pkgbuild_path=path,
                )
                logger.debug("  3 {} {} {}", info, info.package, info.package.packagebase)
                aur_updates_install_info_by_name[pkg_name] = info
        self.aur_updates_install_info += list(aur_updates_install_info_by_name.values())
        logger.debug(">> got install info from PKGBUILDs: {}.", self.aur_updates_install_info)

    def get_aur_deps_info(self) -> None:
        all_aur_pkgs = []
        for info in self.aur_updates_install_info:
            if isinstance(info.package, AURPackageInfo):
                all_aur_pkgs.append(info.package)
            else:
                raise TypeError
        if all_aur_pkgs:
            print_stdout(translate("Resolving AUR dependencies..."))
        try:
            self.aur_deps_relations = find_aur_deps(
                all_aur_pkgs,
                skip_checkdeps_for_pkgnames=self.skip_checkdeps_for_pkgnames,
                skip_runtime_deps=bool(self.args.pkgbuild and (not self.args.install)),
            )
        except DependencyVersionMismatchError as exc:
            if exc.location is not PackageSource.LOCAL:
                raise
            # if local package is too old
            # let's see if a newer one can be found in AUR:
            pkg_name = exc.depends_on
            _aur_pkg_list, not_found_aur_pkgs = find_aur_packages([pkg_name])
            if not_found_aur_pkgs:
                raise
            # start over computing deps and include just found AUR package:
            self.install_package_names.append(pkg_name)
            self.get_all_packages_info()
            return

        # prepare install info (InstallInfo objects)
        # for all the AUR packages which gonna be built:
        # aur_pkgs = {
        #     aur_pkg.name: aur_pkg
        #     for aur_pkg in find_aur_packages(self.aur_deps_names)[0]
        # }
        aur_pkgs = {}
        aur_pkgs_infos, not_found_aur_pkgs = find_aur_packages(self.aur_deps_names)
        provided_aur_deps_infos, not_found_aur_pkgs = find_aur_provided_deps(
            not_found_aur_pkgs,
        )
        for aur_pkg_info in aur_pkgs_infos:
            aur_pkgs[aur_pkg_info.name] = aur_pkg_info
        for aur_pkg_info in provided_aur_deps_infos:
            for provided_pkg_name in aur_pkg_info.provides:
                aur_pkgs[VersionMatcher(provided_pkg_name).pkg_name] = aur_pkg_info
        logger.debug("get_aur_deps_info: aur_pkgs={}", aur_pkgs)

        local_pkgs = PackageDB.get_local_dict()

        added_pkg_names: list[str] = []
        for pkg_name in self.aur_deps_names:
            aur_pkg = aur_pkgs[pkg_name]
            if aur_pkg.name in added_pkg_names:
                continue
            local_pkg = local_pkgs.get(pkg_name)
            self.aur_deps_install_info.append(AURInstallInfo(
                name=aur_pkg.name,
                current_version=local_pkg.version if local_pkg else " ",
                new_version=aur_pkg.version,
                description=aur_pkg.desc,
                maintainer=aur_pkg.maintainer,
                package=aur_pkg,
            ))
            added_pkg_names.append(aur_pkg.name)

    def mark_dependent(self) -> None:
        """Update packages' install info to show deps in prompt."""
        logger.debug(":: marking dependant pkgs...")
        all_provided_pkgs = PackageDB.get_repo_provided_dict()
        all_local_pkgs = PackageDB.get_local_dict()
        all_local_pkgnames = PackageDB.get_local_pkgnames()
        all_deps_install_infos: Sequence[InstallInfo] = (
            self.new_repo_deps_install_info +
            self.new_thirdparty_repo_deps_install_info +
            self.aur_deps_install_info  # type: ignore[operator]
        )
        all_requested_pkg_names = self.install_package_names + functools.reduce(operator.iadd, [
            (
                ii.package.depends + ii.package.makedepends + (
                    ii.package.checkdepends
                    if (ii.name not in self.skip_checkdeps_for_pkgnames)
                    else []
                )
            ) if isinstance(ii.package, AURPackageInfo) else (
                ii.package.depends
            )
            for ii in self.all_install_info
        ], [])
        logger.debug("all_requested_pkg_names={}", all_requested_pkg_names)
        explicit_aur_pkg_names = [ii.name for ii in self.aur_updates_install_info]
        logger.debug("explicit_aur_pkg_names={}", explicit_aur_pkg_names)

        # iterate each package metadata
        for pkg_install_info in self.all_install_info:

            logger.debug(" - {}", pkg_install_info.name)

            # process providers
            provides = pkg_install_info.package.provides
            providing_for: list[str] = []
            if provides and (
                    pkg_install_info.name not in self.install_package_names
            ) and (
                pkg_install_info.name not in explicit_aur_pkg_names
            ) and (
                pkg_install_info.name not in all_local_pkgnames
            ):
                providing_for = [
                    pkg_name for pkg_name in functools.reduce(
                        operator.iadd,
                        [
                            next(
                                [vm.line, vm.pkg_name]
                                for vm in (VersionMatcher(prov), )
                            )
                            for prov in provides
                        ],
                    )
                    if pkg_name in all_requested_pkg_names
                ]
                logger.debug("provides={}", provides, indent=4)
            logger.debug("providing_for={}", providing_for, indent=4)
            for provided_name in providing_for:
                if provided_name in all_provided_pkgs:
                    pkg_install_info.name = provided_name
                    pkg_install_info.provided_by = [
                        provided_dep.package for provided_dep in
                        all_provided_pkgs[provided_name]
                    ]
                    pkg_install_info.new_version = ""

            # process deps
            pkg_dep_lines = (
                (
                    pkg_install_info.package.depends +
                    pkg_install_info.package.makedepends +
                    (
                        pkg_install_info.package.checkdepends
                        if (pkg_install_info.name not in self.skip_checkdeps_for_pkgnames)
                        else []
                    )
                ) if (
                    isinstance(pkg_install_info.package, AURPackageInfo)
                ) else pkg_install_info.package.depends
            )
            for dep_install_info in all_deps_install_infos:
                for name_and_version in (
                        [dep_install_info.package.name] +
                        (dep_install_info.package.provides or [])
                ):
                    name = VersionMatcher(name_and_version).pkg_name
                    if name in [
                            VersionMatcher(dep_line).pkg_name
                            for dep_line in pkg_dep_lines
                    ]:
                        if not dep_install_info.required_by:
                            dep_install_info.required_by = []
                        dep_install_info.required_by.append(pkg_install_info)

                        # if package marked as provider candidate
                        # is already requested as explicit dep for other package
                        # then remove `provided_by` mark and metadata change
                        if (
                                dep_install_info.provided_by
                        ) and (
                            name_and_version == dep_install_info.package.name
                        ):
                            dep_install_info.provided_by = None
                            dep_install_info.name = name
                            dep_install_info.new_version = dep_install_info.package.version

            # process deps for already installed pkgs:
            if (
                    local_pkg := all_local_pkgs.get(pkg_install_info.name)
            ):
                req = local_pkg.compute_requiredby()
                opt = local_pkg.compute_optionalfor()
                pkg_install_info.required_by_installed = req or []
                pkg_install_info.optional_for_installed = opt or []
                pkg_install_info.installed_as_dependency = cast(bool, local_pkg.reason)

        logger.debug("== marked dependant pkgs.")

    def get_total_download_size(self) -> float:
        total_download_size = 0.0
        for install_info in chain.from_iterable(self.repo_install_info_containers):
            total_download_size += install_info.package.size / 1024 ** 2
        return total_download_size

    def get_total_installed_size(self) -> float:
        total_installed_size = 0.0
        for install_info in chain.from_iterable(self.repo_install_info_containers):
            total_installed_size += install_info.package.isize / 1024 ** 2
        return total_installed_size
