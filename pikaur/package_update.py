import sys
from datetime import datetime
from multiprocessing.pool import ThreadPool
from typing import List, Tuple, Optional, Union, Dict

import pyalpm

from .i18n import _, _n
from .core import DataType, PackageSource
from .version import VersionMatcher, compare_versions
from .pacman import (
    OFFICIAL_REPOS,
    PackageDB, PacmanConfig,
    find_packages_not_from_repo, find_upgradeable_packages, get_pacman_command,
)
from .aur import AURPackageInfo, find_aur_packages
from .aur_deps import find_aur_deps, find_repo_deps_of_aur_pkgs
from .pprint import print_stderr, print_stdout
from .args import PikaurArgs, parse_args, reconstruct_args
from .config import PikaurConfig
from .exceptions import PackagesNotFoundInRepo, DependencyVersionMismatch
from .print_department import print_ignored_package, print_not_found_packages


DEVEL_PKGS_POSTFIXES = (
    '-git',
    '-svn',
    '-bzr',
    '-hg',
    '-cvs',
    '-nightly',
)


def is_devel_pkg(pkg_name: str) -> bool:
    result = False
    for devel_pkg_postfix in DEVEL_PKGS_POSTFIXES:
        if pkg_name.endswith(devel_pkg_postfix):
            result = True
            break
    return result


class PackageUpdate(DataType):
    name: str
    current_version: str
    new_version: str
    description: str
    repository: Optional[str] = None
    devel_pkg_age_days: Optional[int] = None
    package: Union[pyalpm.Package, AURPackageInfo]
    provided_by: Optional[List[Union[pyalpm.Package, AURPackageInfo]]] = None
    required_by: Optional[List['PackageUpdate']] = None
    members_of: Optional[List[str]] = None

    def __repr__(self) -> str:
        return (
            f'<{self.__class__.__name__} "{self.name}" '
            f'{self.current_version} -> {self.new_version}>'
        )


def find_repo_updates() -> List[PackageUpdate]:
    all_local_pkgs = PackageDB.get_local_dict()
    repo_packages_updates = []
    for repo_pkg in find_upgradeable_packages():
        local_pkg = all_local_pkgs[repo_pkg.name]
        repo_packages_updates.append(
            PackageUpdate(
                name=local_pkg.name,
                new_version=repo_pkg.version,
                current_version=local_pkg.version,
                description=repo_pkg.desc,
                repository=repo_pkg.db.name,
                package=repo_pkg,
            )
        )
    return repo_packages_updates


def find_aur_devel_updates(
        aur_pkgs_info: List[AURPackageInfo],
        package_ttl_days: int
) -> List[PackageUpdate]:
    local_packages = PackageDB.get_local_dict()
    now = datetime.now()
    aur_updates = []
    for aur_pkg in sorted(aur_pkgs_info, key=lambda x: x.name):
        pkg_name = aur_pkg.name
        if not is_devel_pkg(pkg_name):
            continue
        local_pkg = local_packages[pkg_name]
        pkg_install_datetime = datetime.fromtimestamp(
            local_pkg.installdate
        )
        pkg_age_days = (now - pkg_install_datetime).days
        if pkg_age_days >= package_ttl_days:
            aur_updates.append(PackageUpdate(
                name=pkg_name,
                current_version=local_pkg.version,
                new_version='devel',
                description=aur_pkg.desc,
                devel_pkg_age_days=pkg_age_days,
                package=aur_pkg,
            ))
    return aur_updates


def find_aur_updates(args: PikaurArgs) -> Tuple[List[PackageUpdate], List[str]]:
    package_names = find_packages_not_from_repo()
    print_stderr(_n(
        "Reading AUR package info...",
        "Reading AUR packages info...",
        len(package_names)
    ))
    aur_pkgs_info, not_found_aur_pkgs = find_aur_packages(package_names)
    local_packages = PackageDB.get_local_dict()
    aur_updates = []
    aur_pkgs_up_to_date = []
    for aur_pkg in aur_pkgs_info:
        pkg_name = aur_pkg.name
        aur_version = aur_pkg.version
        current_version = local_packages[pkg_name].version
        compare_aur_pkg = compare_versions(current_version, aur_version)
        if compare_aur_pkg < 0:
            aur_updates.append(PackageUpdate(
                name=pkg_name,
                new_version=aur_version,
                current_version=current_version,
                description=aur_pkg.desc,
                package=aur_pkg,
            ))
        else:
            aur_pkgs_up_to_date.append(aur_pkg)
    if aur_pkgs_up_to_date:
        sync_config = PikaurConfig().sync
        devel_packages_expiration = sync_config.get_int('DevelPkgsExpiration')
        if args.devel:
            devel_packages_expiration = 0
        if devel_packages_expiration > -1:
            aur_updates += find_aur_devel_updates(
                aur_pkgs_up_to_date,
                package_ttl_days=devel_packages_expiration
            )
    return aur_updates, not_found_aur_pkgs


def get_remote_package_version(new_pkg_name: str) -> Optional[str]:
    try:
        repo_info = PackageDB.find_repo_package(new_pkg_name)
    except PackagesNotFoundInRepo:
        aur_packages, _not_found = find_aur_packages([new_pkg_name])
        if aur_packages:
            return aur_packages[0].version
        return None
    else:
        return repo_info.version


class InstallInfoFetcher:

    repo_packages_install_info: List[PackageUpdate]
    new_repo_deps_install_info: List[PackageUpdate]
    thirdparty_repo_packages_install_info: List[PackageUpdate]
    new_thirdparty_repo_deps_install_info: List[PackageUpdate]
    aur_updates_install_info: List[PackageUpdate]
    aur_deps_install_info: List[PackageUpdate]

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
        Retrieve info (`PackageUpdate` objects) of packages
        which are going to be installed/upgraded and their dependencies
        """

        self.exclude_ignored_packages(self.install_package_names)
        # retrieve PackageUpdate objects for repo packages to be installed
        # and their upgrades if --sysupgrade was passed
        self.repo_packages_install_info = []
        self.new_repo_deps_install_info = []
        self.thirdparty_repo_packages_install_info = []
        self.new_thirdparty_repo_deps_install_info = []
        self.aur_updates_install_info = []
        self.aur_deps_install_info = []

        if not self.args.aur:
            self.get_repo_pkgs_info()

        # retrieve PackageUpdate objects for AUR packages to be installed
        # and their upgrades if --sysupgrade was passed
        if not self.args.repo:
            self.get_aur_pkgs_info(self.not_found_repo_pkgs_names)

        # try to find AUR deps for AUR packages
        # if some exception wasn't handled inside -- just write message and exit
        self.get_aur_deps_info()

        self.get_repo_deps_info()

        # update package info to show deps in prompt:
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
        for pkg_install_info in all_install_infos:
            for dep_install_info in all_deps_install_infos:
                for name_and_version in (
                        [dep_install_info.package.name, ] +  # type: ignore
                        (dep_install_info.package.provides or [])
                ):
                    name = VersionMatcher(name_and_version).pkg_name
                    if name in [
                            VersionMatcher(dep_line).pkg_name
                            for dep_line in pkg_install_info.package.depends
                    ]:
                        if not dep_install_info.required_by:
                            dep_install_info.required_by = []
                        dep_install_info.required_by.append(pkg_install_info)

    def _get_repo_pkgs_info(  # pylint: disable=too-many-locals
            self, pkg_names: List[str], extra_args: Optional[List[str]] = None
    ) -> List[PackageUpdate]:
        extra_args = extra_args or []
        all_repo_pkgs = PackageDB.get_repo_dict()
        all_local_pkgs = PackageDB.get_local_dict()

        pacman_args = get_pacman_command(self.args) + [
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
                    install_info = PackageUpdate(
                        name=pkg.name,
                        current_version=local_pkg.version if local_pkg else '',
                        new_version=pkg.version,
                        description=pkg.desc,
                        repository=pkg.db.name,
                        package=pkg,
                    )

                    provides = install_info.package.provides
                    providing_for = [
                        pkg_name for pkg_name in [
                            VersionMatcher(prov).pkg_name
                            for prov in provides
                        ]
                        if pkg_name in self.install_package_names
                    ] if provides else []
                    if providing_for:
                        install_info.name = providing_for[0]
                        install_info.provided_by = [
                            provided_dep.package for provided_dep in
                            PackageDB.get_repo_provided_dict()[providing_for[0]]
                        ]
                        install_info.new_version = ''

                    groups = install_info.package.groups
                    members_of = [
                        gr for gr in groups
                        if gr in self.install_package_names
                    ]
                    if members_of:
                        install_info.members_of = members_of

                    pkg_install_infos.append(install_info)
        return pkg_install_infos

    def get_upgradeable_repo_pkgs_info(self) -> List[PackageUpdate]:
        if not self.args.sysupgrade:
            return []
        all_local_pkgs = PackageDB.get_local_dict()
        pkg_install_infos = []
        for pkg in find_upgradeable_packages():
            local_pkg = all_local_pkgs.get(pkg.name)
            install_info = PackageUpdate(
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
        aur_updates_install_info_by_name: Dict[str, PackageUpdate] = {}
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
            aur_updates_install_info_by_name[pkg_name] = PackageUpdate(
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
        # prepare install info (PackageUpdate objects)
        # for all the AUR packages which gonna be built:
        aur_pkgs = {
            aur_pkg.name: aur_pkg
            for aur_pkg in find_aur_packages(self.aur_deps_names)[0]
        }
        local_pkgs = PackageDB.get_local_dict()
        for pkg_name in self.aur_deps_names:
            aur_pkg = aur_pkgs[pkg_name]
            local_pkg = local_pkgs.get(pkg_name)
            self.aur_deps_install_info.append(PackageUpdate(
                name=pkg_name,
                current_version=local_pkg.version if local_pkg else ' ',
                new_version=aur_pkg.version,
                description=aur_pkg.desc,
                package=aur_pkg,
            ))
