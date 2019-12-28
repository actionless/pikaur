""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

from datetime import datetime
from typing import List, Tuple, Optional, Union

import pyalpm

from .i18n import _n
from .version import compare_versions
from .pacman import (
    PackageDB,
    find_packages_not_from_repo, find_upgradeable_packages,
)
from .aur import AURPackageInfo, find_aur_packages
from .pprint import print_stderr
from .args import parse_args
from .config import PikaurConfig
from .core import InstallInfo
from .exceptions import PackagesNotFoundInRepo
from .print_department import print_ignoring_outofdate_upgrade


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


def get_remote_package(
        new_pkg_name: str
) -> Optional[Union[pyalpm.Package, AURPackageInfo]]:
    try:
        repo_pkg = PackageDB.find_repo_package(new_pkg_name)
    except PackagesNotFoundInRepo:
        aur_packages, _not_found = find_aur_packages([new_pkg_name])
        if aur_packages:
            return aur_packages[0]
        return None
    else:
        return repo_pkg


def get_remote_package_version(new_pkg_name: str) -> Optional[str]:
    pkg = get_remote_package(new_pkg_name)
    if pkg:
        return pkg.version
    return None


def find_repo_upgradeable() -> List[InstallInfo]:
    all_local_pkgs = PackageDB.get_local_dict()
    repo_packages_updates = []
    for repo_pkg in find_upgradeable_packages():
        local_pkg = all_local_pkgs[repo_pkg.name]
        repo_packages_updates.append(
            InstallInfo(
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
) -> List[InstallInfo]:
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
            aur_updates.append(InstallInfo(
                name=pkg_name,
                current_version=local_pkg.version,
                new_version='devel',
                description=aur_pkg.desc,
                devel_pkg_age_days=pkg_age_days,
                package=aur_pkg,
            ))
    return aur_updates


def find_aur_updates() -> Tuple[List[InstallInfo], List[str]]:
    args = parse_args()
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
            pkg_install_info = InstallInfo(
                name=pkg_name,
                new_version=aur_version,
                current_version=current_version,
                description=aur_pkg.desc,
                package=aur_pkg,
            )
            if args.ignore_outofdate and aur_pkg.outofdate:
                print_ignoring_outofdate_upgrade(pkg_install_info)
                continue
            aur_updates.append(pkg_install_info)
        else:
            aur_pkgs_up_to_date.append(aur_pkg)
    if aur_pkgs_up_to_date:
        sync_config = PikaurConfig().sync
        devel_packages_expiration = sync_config.DevelPkgsExpiration.get_int()
        if args.devel:
            devel_packages_expiration = 0
        if devel_packages_expiration > -1:
            aur_updates += find_aur_devel_updates(
                aur_pkgs_up_to_date,
                package_ttl_days=devel_packages_expiration
            )
    return aur_updates, not_found_aur_pkgs
