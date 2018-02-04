
from .core import (
    DataType,
    SingleTaskExecutor,
    compare_versions,
)
from .pacman import PacmanTaskWorker, PackageDB
from .aur import find_aur_packages


class PackageUpdate(DataType):
    Name = None
    Current_Version = None
    New_Version = None
    Description = None


def find_repo_updates():
    result = SingleTaskExecutor(
        PacmanTaskWorker(['-Qu', ])
    ).execute()
    packages_updates_lines = result.stdouts
    repo_packages_updates = []
    repo_pkgs_info = PackageDB.get_repo_dict()
    for update in packages_updates_lines:
        pkg_name, current_version, _, new_version, *_ = update.split()
        repo_packages_updates.append(
            PackageUpdate(
                Name=pkg_name,
                New_Version=new_version,
                Current_Version=current_version,
                Description=repo_pkgs_info[pkg_name].Description,
            )
        )
    return repo_packages_updates


def find_aur_updates(package_versions):
    aur_pkgs_info, not_found_aur_pkgs = find_aur_packages(
        package_versions.keys()
    )
    aur_updates = []
    for result in aur_pkgs_info:
        pkg_name = result['Name']
        aur_version = result['Version']
        current_version = package_versions[pkg_name]
        if compare_versions(current_version, aur_version):
            aur_update = PackageUpdate(
                Name=pkg_name,
                New_Version=aur_version,
                Current_Version=current_version,
                Description=result['Description']
            )
            aur_updates.append(aur_update)
    return aur_updates, not_found_aur_pkgs
