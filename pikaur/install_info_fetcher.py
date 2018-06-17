import sys
from multiprocessing.pool import ThreadPool
from typing import List, Optional, Dict

from .i18n import _
from .core import PackageSource, InstallInfo
from .version import VersionMatcher
from .pacman import (
    OFFICIAL_REPOS,
    PackageDB, PacmanConfig,
    find_upgradeable_packages, get_pacman_command,
)
from .aur import find_aur_packages, AURPackageInfo
from .aur_deps import find_aur_deps, find_repo_deps_of_aur_pkgs
from .pprint import print_stdout
from .args import PikaurArgs, parse_args, reconstruct_args
from .exceptions import DependencyVersionMismatch
from .print_department import print_ignored_package, print_not_found_packages
from .updates import find_aur_updates


class InstallInfoFetcher:

    repo_packages_install_info: List[InstallInfo]
    new_repo_deps_install_info: List[InstallInfo]
    thirdparty_repo_packages_install_info: List[InstallInfo]
    new_thirdparty_repo_deps_install_info: List[InstallInfo]
    aur_updates_install_info: List[InstallInfo]
    aur_deps_install_info: List[InstallInfo]

    args: PikaurArgs
    aur_deps_relations: Dict[str, List[str]]

    def __init__(
            self,
            install_package_names: List[str],
            not_found_repo_pkgs_names: List[str],
            manually_excluded_packages_names: List[str],
    ) -> None:
        self.args = parse_args()
        self.install_package_names = install_package_names
        self.not_found_repo_pkgs_names = not_found_repo_pkgs_names
        self.manually_excluded_packages_names = manually_excluded_packages_names

        self.get_all_packages_info()

    def package_is_ignored(self, package_name: str) -> bool:
        if (
                package_name in (
                    (self.args.ignore or []) + PacmanConfig().options.get('IgnorePkg', [])
                )
        ) and not (
            package_name in self.install_package_names or
            package_name in self.not_found_repo_pkgs_names
        ):
            return True
        return False

    def exclude_ignored_packages(self, package_names: List[str]) -> None:
        ignored_packages = []
        for pkg_name in package_names[:]:
            if self.package_is_ignored(pkg_name):
                package_names.remove(pkg_name)
                ignored_packages.append(pkg_name)

        for package_name in ignored_packages:
            print_ignored_package(package_name)

    @property
    def aur_deps_names(self) -> List[str]:
        _aur_deps_names: List[str] = []
        for deps in self.aur_deps_relations.values():
            _aur_deps_names += deps
        return list(set(_aur_deps_names))

    def get_all_packages_info(self) -> None:  # pylint:disable=too-many-branches
        """
        Retrieve info (`InstallInfo` objects) of packages
        which are going to be installed/upgraded and their dependencies
        """

        self.exclude_ignored_packages(self.install_package_names)

        self.repo_packages_install_info = []
        self.new_repo_deps_install_info = []
        self.thirdparty_repo_packages_install_info = []
        self.new_thirdparty_repo_deps_install_info = []
        self.aur_updates_install_info = []
        self.aur_deps_install_info = []

        # retrieve InstallInfo objects for repo packages to be installed
        # and their upgrades if --sysupgrade was passed
        if not self.args.aur:
            self.get_repo_pkgs_info()

        # retrieve InstallInfo objects for AUR packages to be installed
        # and their upgrades if --sysupgrade was passed
        if not self.args.repo:
            self.get_aur_pkgs_info(self.not_found_repo_pkgs_names)

        # try to find AUR deps for AUR packages
        # if some exception wasn't handled inside -- just write message and exit
        self.get_aur_deps_info()

        # find repo deps for AUR packages
        self.get_repo_deps_info()

        self.mark_dependent()

    def _get_repo_pkgs_info(  # pylint: disable=too-many-locals
            self, pkg_names: List[str], extra_args: Optional[List[str]] = None
    ) -> List[InstallInfo]:
        extra_args = extra_args or []
        all_repo_pkgs = PackageDB.get_repo_dict()
        all_local_pkgs = PackageDB.get_local_dict()

        pacman_args = get_pacman_command() + [
            '--sync',
        ] + reconstruct_args(self.args, ignore_args=[
            'sync',
            'refresh',
            'ignore',
            'sysupgrade',
        ])

        pkg_install_infos = []
        all_results = {}
        with ThreadPool() as pool:
            all_requests = {}
            for pkg_name in pkg_names[:]:
                all_requests[pkg_name] = pool.apply_async(
                    PackageDB.get_print_format_output,
                    (pacman_args + [pkg_name], )
                )
            pool.close()
            pool.join()
            for pkg_name, request in all_requests.items():
                all_results[pkg_name] = request.get()
        for pkg_name, results in all_results.items():
            if not results:
                self.not_found_repo_pkgs_names.append(pkg_name)
                if pkg_name in self.install_package_names:
                    self.install_package_names.remove(pkg_name)
            else:
                for pkg_print in results:
                    pkg = all_repo_pkgs[pkg_print.full_name]
                    local_pkg = all_local_pkgs.get(pkg.name)
                    install_info = InstallInfo(
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

                    pkg_install_infos.append(install_info)
        return pkg_install_infos

    def get_upgradeable_repo_pkgs_info(self) -> List[InstallInfo]:
        if not self.args.sysupgrade:
            return []
        all_local_pkgs = PackageDB.get_local_dict()
        pkg_install_infos = []
        for pkg in find_upgradeable_packages():
            local_pkg = all_local_pkgs.get(pkg.name)
            install_info = InstallInfo(
                name=pkg.name,
                current_version=local_pkg.version if local_pkg else '',
                new_version=pkg.version,
                description=pkg.desc,
                repository=pkg.db.name,
                package=pkg,
            )
            pkg_install_infos.append(install_info)
        return pkg_install_infos

    def get_repo_pkgs_info(self):
        for pkg_update in (
                self._get_repo_pkgs_info(pkg_names=self.install_package_names) +
                self.get_upgradeable_repo_pkgs_info()
        ):
            if pkg_update.name in [
                    install_info.name for install_info in
                    (
                        self.repo_packages_install_info +
                        self.thirdparty_repo_packages_install_info +
                        self.new_repo_deps_install_info +
                        self.new_thirdparty_repo_deps_install_info
                    )
            ]:
                continue

            pkg_name = pkg_update.name
            if (
                    pkg_name in self.manually_excluded_packages_names
            ) or (
                self.package_is_ignored(pkg_name)
            ):
                print_ignored_package(pkg_name)
                # if pkg_name not in self.manually_excluded_packages_names:
                    # self.manually_excluded_packages_names.append(pkg_name)
                continue

            if pkg_update.current_version == '' and (
                    (
                        pkg_name not in self.install_package_names
                    ) and (not pkg_update.provided_by) and (not pkg_update.members_of)
            ):
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
        all_aur_pkg_names = [
            pkg_info.name for pkg_info in self.aur_updates_install_info + self.aur_deps_install_info
        ]
        new_dep_names = find_repo_deps_of_aur_pkgs(all_aur_pkg_names)

        for dep_install_info in self._get_repo_pkgs_info(
                pkg_names=new_dep_names, extra_args=['--needed']
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

    def get_aur_pkgs_info(self, aur_packages_names: List[str]):
        local_pkgs = PackageDB.get_local_dict()
        aur_pkg_list, not_found_aur_pkgs = find_aur_packages(aur_packages_names)
        if not_found_aur_pkgs:
            print_not_found_packages(sorted(not_found_aur_pkgs))
            sys.exit(6)
        aur_pkgs = {
            aur_pkg.name: aur_pkg
            for aur_pkg in aur_pkg_list
        }
        aur_updates_install_info_by_name: Dict[str, InstallInfo] = {}
        if self.args.sysupgrade:
            aur_updates_list, not_found_aur_pkgs = find_aur_updates(self.args)
            self.exclude_ignored_packages(not_found_aur_pkgs)
            if not_found_aur_pkgs:
                print_not_found_packages(sorted(not_found_aur_pkgs))
            aur_updates_install_info_by_name = {
                upd.name: upd for upd in aur_updates_list
            }
        for pkg_name, aur_pkg in aur_pkgs.items():
            if pkg_name in aur_updates_install_info_by_name:
                continue
            local_pkg = local_pkgs.get(pkg_name)
            aur_updates_install_info_by_name[pkg_name] = InstallInfo(
                name=pkg_name,
                current_version=local_pkg.version if local_pkg else ' ',
                new_version=aur_pkg.version,
                description=aur_pkg.desc,
                package=aur_pkg,
            )
        for pkg_name in list(aur_updates_install_info_by_name.keys())[:]:
            if (
                    pkg_name in self.manually_excluded_packages_names
            ) or (
                self.package_is_ignored(pkg_name)
            ):
                print_ignored_package(pkg_name)
                del aur_updates_install_info_by_name[pkg_name]
        self.aur_updates_install_info = list(aur_updates_install_info_by_name.values())

    def get_aur_deps_info(self):
        all_aur_packages_names = [info.name for info in self.aur_updates_install_info]
        if all_aur_packages_names:
            print_stdout(_("Resolving AUR dependencies..."))
        try:
            self.aur_deps_relations = find_aur_deps(all_aur_packages_names)
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
            self.aur_deps_install_info.append(InstallInfo(
                name=pkg_name,
                current_version=local_pkg.version if local_pkg else ' ',
                new_version=aur_pkg.version,
                description=aur_pkg.desc,
                package=aur_pkg,
            ))

    def mark_dependent(self) -> None:
        """
        update packages' install info to show deps in prompt:
        """
        all_provided_pkgs = PackageDB.get_repo_provided_dict()
        all_install_infos = (
            self.repo_packages_install_info +
            self.thirdparty_repo_packages_install_info +
            self.new_repo_deps_install_info +
            self.new_thirdparty_repo_deps_install_info +
            self.aur_updates_install_info +
            self.aur_deps_install_info
        )
        all_deps_install_infos = (
            self.new_repo_deps_install_info +
            self.new_thirdparty_repo_deps_install_info +
            self.aur_deps_install_info
        )

        all_requested_pkg_names = self.install_package_names + sum([
            (
                ii.package.depends + ii.package.makedepends + ii.package.checkdepends
            ) if isinstance(ii.package, AURPackageInfo) else (
                ii.package.depends
            )
            for ii in all_install_infos
        ], [])

        for pkg_install_info in all_install_infos:

            provides = pkg_install_info.package.provides
            providing_for: List[str] = []
            if provides and pkg_install_info.name not in self.install_package_names:
                providing_for = [
                    pkg_name for pkg_name in sum([
                        (lambda vm: [vm.line, vm.pkg_name])(VersionMatcher(prov))
                        for prov in provides
                    ], [])
                    if pkg_name in all_requested_pkg_names
                ]
            if providing_for:
                provided_name = providing_for[0]
                if provided_name in all_provided_pkgs:
                    pkg_install_info.name = provided_name
                    pkg_install_info.provided_by = [
                        provided_dep.package for provided_dep in
                        all_provided_pkgs[provided_name]
                    ]
                    pkg_install_info.new_version = ''

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
                        [dep_install_info.package.name, ] +  # type: ignore
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
