""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """
from itertools import chain
from multiprocessing.pool import ThreadPool
from typing import List, Optional, Dict, Sequence, Union

from .i18n import translate
from .core import (
    PackageSource, InstallInfo, AURInstallInfo, RepoInstallInfo, ComparableType,
)
from .version import VersionMatcher
from .pacman import (
    OFFICIAL_REPOS,
    PackageDB, PacmanConfig, PacmanPrint,
    find_sysupgrade_packages, get_pacman_command, strip_repo_name,
    get_ignored_pkgnames_from_patterns,
)
from .aur import find_aur_packages, AURPackageInfo, strip_aur_repo_name
from .aur_deps import find_aur_deps, find_repo_deps_of_aur_pkgs
from .pprint import print_stdout, print_stderr, create_debug_logger, print_error
from .args import PikaurArgs, parse_args, reconstruct_args
from .exceptions import DependencyVersionMismatch, DependencyError, SysExit
from .print_department import print_ignored_package, print_not_found_packages
from .updates import find_aur_updates, print_upgradeable
from .replacements import find_replacements
from .srcinfo import SrcInfo
from .prompt import ask_to_continue


_debug = create_debug_logger('install_info_fetcher')


class InstallInfoFetcher(ComparableType):  # pylint: disable=too-many-public-methods

    repo_packages_install_info: List[RepoInstallInfo]
    new_repo_deps_install_info: List[RepoInstallInfo]
    thirdparty_repo_packages_install_info: List[RepoInstallInfo]
    new_thirdparty_repo_deps_install_info: List[RepoInstallInfo]
    repo_replacements_install_info: List[RepoInstallInfo]
    thirdparty_repo_replacements_install_info: List[RepoInstallInfo]
    aur_updates_install_info: List[AURInstallInfo]
    aur_deps_install_info: List[AURInstallInfo]

    args: PikaurArgs
    aur_deps_relations: Dict[str, List[str]]
    replacements: Dict[str, List[str]]

    __ignore_in_eq__ = ('args', )

    def __init__(
            self,
            install_package_names: List[str],
            not_found_repo_pkgs_names: List[str],
            manually_excluded_packages_names: List[str],
            pkgbuilds_packagelists: Dict[str, List[str]],
    ) -> None:
        _debug(f"""Gonna fetch install info for:
    {install_package_names=}
    {not_found_repo_pkgs_names=}
    {pkgbuilds_packagelists=}
    {manually_excluded_packages_names=}
""")
        self.args = parse_args()
        self.install_package_names = install_package_names
        self.not_found_repo_pkgs_names = not_found_repo_pkgs_names
        self.manually_excluded_packages_names = manually_excluded_packages_names
        self.pkgbuilds_packagelists = pkgbuilds_packagelists
        self.replacements = find_replacements() if self.args.sysupgrade else {}

        self.get_all_packages_info()
        if self.args.sysupgrade:
            # print ignored package updates:
            print_upgradeable(
                ignored_only=True,
                install_infos=self.all_install_info
            )

    def package_is_ignored(self, package_name: str) -> bool:
        ignored_pkg_names = get_ignored_pkgnames_from_patterns(
            [package_name],
            self.args.ignore + PacmanConfig().options.get('IgnorePkg', [])
        )
        if (
                package_name in ignored_pkg_names
        ) and not (
            package_name in self.install_package_names or
            package_name in self.not_found_repo_pkgs_names
        ):
            return True
        return False

    def exclude_ignored_packages(
            self,
            package_names: List[str],
            print_packages=True
    ) -> None:
        ignored_packages = []
        for pkg_name in package_names[:]:
            if self.package_is_ignored(pkg_name):
                package_names.remove(pkg_name)
                ignored_packages.append(pkg_name)
        if print_packages:
            for package_name in ignored_packages:
                print_ignored_package(package_name=package_name)

    @property
    def aur_packages_names(self) -> List[str]:
        return [
            pkg_info.name for pkg_info in self.aur_updates_install_info
        ]

    @property
    def aur_deps_names(self) -> List[str]:
        _aur_deps_names: List[str] = []
        for deps in self.aur_deps_relations.values():
            _aur_deps_names += deps
        return list(set(_aur_deps_names))

    @property
    def aur_install_info_containers(self) -> Sequence[List[AURInstallInfo]]:
        return (
            self.aur_updates_install_info,
            self.aur_deps_install_info,
        )

    @property
    def repo_install_info_containers(self) -> Sequence[List[RepoInstallInfo]]:
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
            self
    ) -> Sequence[Union[List[RepoInstallInfo], List[AURInstallInfo]]]:
        return (
            *self.repo_install_info_containers,
            *self.aur_install_info_containers,
        )

    @property
    def repo_install_info(self) -> Sequence[RepoInstallInfo]:
        return list(
            info
            for infos in self.repo_install_info_containers
            for info in infos
        )

    @property
    def aur_install_info(self) -> Sequence[AURInstallInfo]:
        return list(
            info
            for infos in self.aur_install_info_containers
            for info in infos
        )

    @property
    def all_install_info(self) -> Sequence[Union[RepoInstallInfo, AURInstallInfo]]:
        return list(self.repo_install_info) + list(self.aur_install_info)

    def discard_package(
            self, canceled_pkg_name: str, already_discarded: List[str] = None
    ) -> List[str]:
        _debug(f"discarding {canceled_pkg_name=}")
        for container in self.all_install_info_containers:
            for info in container[:]:
                if info.name == canceled_pkg_name:
                    container.remove(info)  # type: ignore[arg-type]

        already_discarded = (already_discarded or []) + [canceled_pkg_name]
        for aur_pkg_name, aur_deps in list(self.aur_deps_relations.items())[:]:
            if canceled_pkg_name == aur_pkg_name:
                _debug(f"{aur_pkg_name=}: {aur_deps=}")
                for pkg_name in aur_deps + [aur_pkg_name]:
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

        # retrieve InstallInfo objects for repo packages to be installed
        # and their upgrades if --sysupgrade was passed
        if not self.args.aur:
            _debug("Gonna get repo pkgs install info...")
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

    def _get_repo_pkgs_info(  # pylint: disable=too-many-statements,too-many-locals,too-many-branches
            self, pkg_lines: List[str], extra_args: Optional[List[str]] = None
    ) -> List[RepoInstallInfo]:
        if not pkg_lines:
            return []

        extra_args = extra_args or []
        all_repo_pkgs = PackageDB.get_repo_dict()
        all_local_pkgs = PackageDB.get_local_dict()

        # pacman print-info flag conflicts with some normal --sync options:
        pacman_args = get_pacman_command(ignore_args=[
            'overwrite'
        ]) + [
            '--sync',
        ] + reconstruct_args(self.args, ignore_args=[
            'sync',
            'ignore',
            'sysupgrade',
            'refresh',
            'needed',
            'verbose',
            'overwrite',
            'search',
        ]) + extra_args

        def _get_pkg_install_infos(results: List[PacmanPrint]) -> List[RepoInstallInfo]:
            install_infos = []
            for pkg_print in results:
                pkg = all_repo_pkgs[pkg_print.full_name]
                local_pkg = all_local_pkgs.get(pkg.name)
                install_info = RepoInstallInfo(
                    name=pkg.name,
                    current_version=local_pkg.version if local_pkg else '',
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
            _debug(f"Checking if '{pkg_lines=}' is installable:")
            composed_result = PackageDB.get_print_format_output(
                pacman_args + [
                    pkg
                    for pkg_line in pkg_lines
                    for pkg in pkg_line.split(',')
                ]
            )
        except DependencyError:
            _debug("Check failed - gonna check it separately:")
            composed_result = []
        if composed_result:
            _debug("Check passed - gonna get install infos:")
            return _get_pkg_install_infos(composed_result)

        all_results = {}
        with ThreadPool() as pool:
            pkg_exists_requests = {}
            for pkg_name in pkg_lines[:]:
                _debug(f"Checking if '{pkg_name}' exists in the repo:")
                pkg_exists_requests[pkg_name] = pool.apply_async(
                    PackageDB.get_print_format_output,
                    (pacman_args + pkg_name.split(','), False, True)
                )
            pool.close()
            pool.join()
            for pkg_name, request in pkg_exists_requests.items():
                try:
                    all_results[pkg_name] = request.get()
                    _debug(f"  '{pkg_name}' is found in the repo.")
                except DependencyError:
                    all_results[pkg_name] = []
                    _debug(f"  '{pkg_name}' is NOT found in the repo.")

        with ThreadPool() as pool:
            pkg_installable_requests = {}
            for pkg_name, results in all_results.items():
                if not results:
                    continue
                _debug(f"Checking if '{pkg_name}' is installable:")
                pkg_installable_requests[pkg_name] = pool.apply_async(
                    PackageDB.get_print_format_output,
                    (pacman_args + pkg_name.split(','), )
                )
            pool.close()
            pool.join()
            for pkg_name, request in pkg_installable_requests.items():
                try:
                    request.get()
                    _debug(f"  '{pkg_name}' is installable.")
                except DependencyError as exc:
                    print_error(f"'{pkg_name}' is NOT installable.")
                    print_stderr(str(exc))
                    if not ask_to_continue:
                        raise SysExit(125) from exc

        _debug("Check partially passed - gonna get install infos:")
        pkg_install_infos: List[RepoInstallInfo] = []
        for pkg_name, results in all_results.items():
            if not results:
                self.not_found_repo_pkgs_names.append(pkg_name)
                if pkg_name in self.install_package_names:
                    self.install_package_names.remove(pkg_name)
            else:
                pkg_install_infos += _get_pkg_install_infos(results)
        return pkg_install_infos

    def get_upgradeable_repo_pkgs_info(self) -> List[RepoInstallInfo]:
        if not self.args.sysupgrade:
            return []
        all_local_pkgs = PackageDB.get_local_dict()
        pkg_install_infos = []
        for pkg in find_sysupgrade_packages(ignore_pkgs=self.manually_excluded_packages_names):
            local_pkg = all_local_pkgs.get(pkg.name)
            install_info = RepoInstallInfo(
                name=pkg.name,
                current_version=local_pkg.version if local_pkg else '',
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
            if pkg_update.name in self.repo_install_info:
                continue

            pkg_name = pkg_update.name
            if (
                    self.package_is_manually_excluded(pkg_name)
            ) or (
                self.package_is_ignored(pkg_name)
            ):
                # @TODO: probably this branch is never called anymore
                print_ignored_package(install_info=pkg_update)
                continue

            if pkg_update.current_version == '' and (
                    (
                        pkg_name not in self.install_package_names
                    ) and (not pkg_update.provided_by) and (not pkg_update.members_of)
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
        all_aur_pkgs: List[AURPackageInfo] = [
            pkg_info.package
            for pkg_info in self.aur_updates_install_info + self.aur_deps_install_info
        ]
        new_dep_version_matchers = find_repo_deps_of_aur_pkgs(all_aur_pkgs)
        new_dep_lines = [
            vm.line for vm in new_dep_version_matchers
        ]

        for dep_install_info in self._get_repo_pkgs_info(
                pkg_lines=new_dep_lines, extra_args=['--needed']
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

    def get_aur_pkgs_info(self, aur_packages_versionmatchers: List[str]) -> None:  # pylint: disable=too-many-branches
        aur_packages_names_to_versions = {
            strip_aur_repo_name(version_matcher.pkg_name): version_matcher
            for version_matcher in [VersionMatcher(name) for name in aur_packages_versionmatchers]
        }
        _debug(
            f"gonna get AUR pkgs install info for:\n"
            f"    {aur_packages_versionmatchers=}\n"
            f"    {self.aur_updates_install_info=}\n"
            f"    {aur_packages_names_to_versions=}"
        )
        local_pkgs = PackageDB.get_local_dict()
        aur_pkg_list, not_found_aur_pkgs = find_aur_packages(
            list(aur_packages_names_to_versions.keys())
        )
        _debug(
            f"found AUR pkgs:\n"
            f"    {aur_pkg_list=}\n"
            f"    {not_found_aur_pkgs=}\n"
        )
        aur_pkgs = {}
        for aur_pkg in aur_pkg_list:
            if aur_packages_names_to_versions[aur_pkg.name](aur_pkg.version):
                aur_pkgs[aur_pkg.name] = aur_pkg
            else:
                not_found_aur_pkgs.append(aur_packages_names_to_versions[aur_pkg.name].line)
        if not_found_aur_pkgs:
            print_not_found_packages(sorted(not_found_aur_pkgs))
            raise SysExit(6)
        aur_updates_install_info_by_name: Dict[str, AURInstallInfo] = {}
        if self.args.sysupgrade:
            aur_updates_list, not_found_aur_pkgs = find_aur_updates()
            self.exclude_ignored_packages(not_found_aur_pkgs, print_packages=False)
            if not_found_aur_pkgs:
                print_not_found_packages(sorted(not_found_aur_pkgs))
            aur_updates_install_info_by_name = {
                upd.name: upd for upd in aur_updates_list
            }
        for pkg_name, aur_pkg in aur_pkgs.items():
            if pkg_name in aur_updates_install_info_by_name:
                continue
            local_pkg = local_pkgs.get(pkg_name)
            aur_updates_install_info_by_name[pkg_name] = AURInstallInfo(
                name=pkg_name,
                current_version=local_pkg.version if local_pkg else ' ',
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
                print_ignored_package(
                    install_info=aur_updates_install_info_by_name[pkg_name]
                )
                del aur_updates_install_info_by_name[pkg_name]
            for pkg_list in self.pkgbuilds_packagelists.values():
                if pkg_name in pkg_list:
                    del aur_updates_install_info_by_name[pkg_name]
        self.aur_updates_install_info += list(aur_updates_install_info_by_name.values())
        _debug(f"got AUR pkgs install info: {self.aur_updates_install_info=}")

    def get_info_from_pkgbuilds(self) -> None:
        _debug(f"gonna get install info from PKGBUILDs... {self.aur_updates_install_info=}")
        aur_updates_install_info_by_name: Dict[str, AURInstallInfo] = {}
        local_pkgs = PackageDB.get_local_dict()
        for path, pkg_names in self.pkgbuilds_packagelists.items():
            if not pkg_names:
                common_srcinfo = SrcInfo(pkgbuild_path=path)
                common_srcinfo.regenerate()
                pkg_names = common_srcinfo.pkgnames
            for pkg_name in pkg_names:
                if pkg_name in self.manually_excluded_packages_names:
                    continue
                srcinfo = SrcInfo(pkgbuild_path=path, package_name=pkg_name)
                aur_pkg = AURPackageInfo.from_srcinfo(srcinfo)
                if pkg_name in aur_updates_install_info_by_name:
                    raise Exception(translate(f"{pkg_name} already added to the list"))
                local_pkg = local_pkgs.get(pkg_name)
                aur_updates_install_info_by_name[pkg_name] = AURInstallInfo(
                    name=pkg_name,
                    current_version=local_pkg.version if local_pkg else ' ',
                    new_version=aur_pkg.version,
                    description=aur_pkg.desc,
                    maintainer='local user',
                    package=aur_pkg,
                    pkgbuild_path=path,
                )
        self.aur_updates_install_info += list(aur_updates_install_info_by_name.values())
        _debug(f"got install info from PKGBUILDs... {self.aur_updates_install_info=}")

    def get_aur_deps_info(self) -> None:
        all_aur_pkgs = []
        for info in self.aur_updates_install_info:
            if isinstance(info.package, AURPackageInfo):
                all_aur_pkgs.append(info.package)
            else:
                raise TypeError()
        if all_aur_pkgs:
            print_stdout(translate("Resolving AUR dependencies..."))
        try:
            self.aur_deps_relations = find_aur_deps(all_aur_pkgs)
        except DependencyVersionMismatch as exc:
            if exc.location is not PackageSource.LOCAL:
                raise exc
            # if local package is too old
            # let's see if a newer one can be found in AUR:
            pkg_name = exc.depends_on
            _aur_pkg_list, not_found_aur_pkgs = find_aur_packages([pkg_name, ])
            if not_found_aur_pkgs:
                raise exc
            # start over computing deps and include just found AUR package:
            self.install_package_names.append(pkg_name)
            self.get_all_packages_info()
            return
        # prepare install info (InstallInfo objects)
        # for all the AUR packages which gonna be built:
        aur_pkgs = {
            aur_pkg.name: aur_pkg
            for aur_pkg in find_aur_packages(self.aur_deps_names)[0]
        }
        local_pkgs = PackageDB.get_local_dict()
        for pkg_name in self.aur_deps_names:
            aur_pkg = aur_pkgs[pkg_name]
            local_pkg = local_pkgs.get(pkg_name)
            self.aur_deps_install_info.append(AURInstallInfo(
                name=pkg_name,
                current_version=local_pkg.version if local_pkg else ' ',
                new_version=aur_pkg.version,
                description=aur_pkg.desc,
                maintainer=aur_pkg.maintainer,
                package=aur_pkg,
            ))

    def mark_dependent(self) -> None:
        """
        update packages' install info to show deps in prompt:
        """

        all_provided_pkgs = PackageDB.get_repo_provided_dict()
        all_local_pkgnames = PackageDB.get_local_pkgnames()
        all_deps_install_infos: Sequence[InstallInfo] = (
            self.new_repo_deps_install_info +
            self.new_thirdparty_repo_deps_install_info +
            self.aur_deps_install_info  # type: ignore[operator]
        )
        all_requested_pkg_names = self.install_package_names + sum([
            (
                ii.package.depends + ii.package.makedepends + ii.package.checkdepends
            ) if isinstance(ii.package, AURPackageInfo) else (
                ii.package.depends
            )
            for ii in self.all_install_info
        ], [])
        explicit_aur_pkg_names = [ii.name for ii in self.aur_updates_install_info]

        # iterate each package metadata
        for pkg_install_info in self.all_install_info:

            # process providers
            provides = pkg_install_info.package.provides
            providing_for: List[str] = []
            if provides and (
                    pkg_install_info.name not in self.install_package_names
            ) and (
                pkg_install_info.name not in explicit_aur_pkg_names
            ) and (
                pkg_install_info.name not in all_local_pkgnames
            ):
                providing_for = [
                    pkg_name for pkg_name in sum([
                        # pylint: disable=unnecessary-direct-lambda-call
                        (lambda vm: [vm.line, vm.pkg_name])(VersionMatcher(prov))
                        for prov in provides
                    ], [])
                    if pkg_name in all_requested_pkg_names
                ]
            for provided_name in providing_for:
                if provided_name in all_provided_pkgs:
                    pkg_install_info.name = provided_name
                    pkg_install_info.provided_by = [
                        provided_dep.package for provided_dep in
                        all_provided_pkgs[provided_name]
                    ]
                    pkg_install_info.new_version = ''

            # process deps
            pkg_dep_lines = (
                (
                    pkg_install_info.package.depends +
                    pkg_install_info.package.makedepends +
                    pkg_install_info.package.checkdepends
                ) if (
                    isinstance(pkg_install_info.package, AURPackageInfo)
                ) else pkg_install_info.package.depends
            )
            for dep_install_info in all_deps_install_infos:
                for name_and_version in (
                        [dep_install_info.package.name, ] +
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
