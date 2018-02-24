from .core import (
    DataType, SingleTaskExecutor,
)
from .version import compare_versions
from .pacman import PacmanTaskWorker, PackageDB
from .aur import find_aur_packages


class PackageUpdate(DataType):
    Name = None
    Current_Version = None
    New_Version = None
    Description = None
    Repository = None

    def __repr__(self):
        return (
            f'<{self.__class__.__name__} "{self.Name}" '
            f'{self.Current_Version} -> {self.New_Version}>'
        )


def find_repo_updates():
    result = SingleTaskExecutor(
        PacmanTaskWorker(['-Qu', ])
    ).execute()
    packages_updates_lines = result.stdouts
    repo_packages_updates = []
    repo_pkgs_info = PackageDB.get_repo_dict()
    for update in packages_updates_lines:
        pkg_name, current_version, _, new_version, *_ = update.split()
        pkg_info = repo_pkgs_info[pkg_name]
        repo_packages_updates.append(
            PackageUpdate(
                Name=pkg_name,
                New_Version=new_version,
                Current_Version=current_version,
                Description=pkg_info.Description,
            )
        )
    return repo_packages_updates


def find_aur_updates(package_versions):
    aur_pkgs_info, not_found_aur_pkgs = find_aur_packages(
        package_versions.keys()
    )
    aur_updates = []
    for result in aur_pkgs_info:
        pkg_name = result.Name
        aur_version = result.Version
        current_version = package_versions[pkg_name]
        compare_result = compare_versions(current_version, aur_version)
        if compare_result < 0:
            aur_updates.append(PackageUpdate(
                Name=pkg_name,
                New_Version=aur_version,
                Current_Version=current_version,
                Description=result.Description
            ))
    return aur_updates, not_found_aur_pkgs
