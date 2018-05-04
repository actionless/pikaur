from datetime import datetime
from typing import List, Tuple, Optional

import pyalpm

from .core import DataType
from .i18n import _n
from .version import compare_versions
from .pacman import PackageDB, find_packages_not_from_repo
from .aur import AURPackageInfo, find_aur_packages
from .pprint import print_status_message
from .args import PikaurArgs
from .config import PikaurConfig


DEVEL_PKGS_POSTFIXES = (
    '-git',
    '-svn',
    '-bzr',
    '-hg',
    '-cvs',
)


def is_devel_pkg(pkg_name: str) -> bool:
    result = False
    for devel_pkg_postfix in DEVEL_PKGS_POSTFIXES:
        if pkg_name.endswith(devel_pkg_postfix):
            result = True
            break
    return result


class PackageUpdate(DataType):
    # @TODO: use lowercase properties
    Name: str
    Current_Version: str
    New_Version: str
    Description: str
    Repository: str
    devel_pkg_age_days: Optional[int] = None

    def __repr__(self) -> str:
        return (
            f'<{self.__class__.__name__} "{self.Name}" '
            f'{self.Current_Version} -> {self.New_Version}>'
        )


def find_repo_updates() -> List[PackageUpdate]:
    repo_packages_updates = []
    for local_pkg in PackageDB.get_local_list():
        repo_pkg = pyalpm.sync_newversion(
            local_pkg, PackageDB.get_alpm_handle().get_syncdbs()
        )
        if not repo_pkg:
            continue
        repo_packages_updates.append(
            PackageUpdate(
                Name=local_pkg.name,
                New_Version=repo_pkg.version,
                Current_Version=local_pkg.version,
                Description=repo_pkg.desc,
                Repository=repo_pkg.db.name,
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
                Name=pkg_name,
                Current_Version=local_pkg.version,
                New_Version='devel',
                Description=aur_pkg.desc,
                devel_pkg_age_days=pkg_age_days
            ))
    return aur_updates


def find_aur_updates(args: PikaurArgs) -> Tuple[List[PackageUpdate], List[str]]:
    package_names = find_packages_not_from_repo()
    print_status_message(_n("Reading AUR package info...",
                            "Reading AUR packages info...",
                            len(package_names)))
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
                Name=pkg_name,
                New_Version=aur_version,
                Current_Version=current_version,
                Description=aur_pkg.desc
            ))
        else:
            aur_pkgs_up_to_date.append(aur_pkg)
    if aur_pkgs_up_to_date:
        sync_config = PikaurConfig().sync
        devel_packages_expiration: int = sync_config.get('DevelPkgsExpiration')  # type: ignore
        if args.devel:
            devel_packages_expiration = 0
        if devel_packages_expiration > -1:
            aur_updates += find_aur_devel_updates(
                aur_pkgs_up_to_date,
                package_ttl_days=devel_packages_expiration
            )
    return aur_updates, not_found_aur_pkgs


def get_remote_package_version(new_pkg_name: str) -> Optional[str]:
    repo_info = PackageDB.get_repo_dict().get(new_pkg_name)
    if repo_info:
        return repo_info.version
    aur_packages, _not_found = find_aur_packages([new_pkg_name])
    if aur_packages:
        return aur_packages[0].version
    return None
