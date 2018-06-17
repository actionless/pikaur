from datetime import datetime
from typing import List, Tuple, Optional, Union

import pyalpm

from .core import DataType
from .i18n import _n
from .version import compare_versions
from .pacman import (
    PackageDB,
    find_packages_not_from_repo, find_upgradeable_packages,
)
from .aur import AURPackageInfo, find_aur_packages
from .pprint import print_stderr
from .args import PikaurArgs
from .config import PikaurConfig
from .exceptions import PackagesNotFoundInRepo


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
