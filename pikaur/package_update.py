from .core import (
    DataType,
    SingleTaskExecutor, MultipleTasksExecutorPool
)
from .version import compare_versions_async
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


class FindAurUpdatesTask():

    def __init__(self, package_versions, result):
        self.package_versions = package_versions
        self.result = result

    async def get_task(self, _loop):
        result = self.result
        package_versions = self.package_versions

        pkg_name = result.Name
        aur_version = result.Version
        current_version = package_versions[pkg_name]
        compare_result = await compare_versions_async(current_version, aur_version)
        if compare_result > 0:
            aur_update = PackageUpdate(
                Name=pkg_name,
                New_Version=aur_version,
                Current_Version=current_version,
                Description=result.Description
            )
            return aur_update


def find_aur_updates(package_versions):
    aur_pkgs_info, not_found_aur_pkgs = find_aur_packages(
        package_versions.keys()
    )
    aur_updates = [
        update for update in MultipleTasksExecutorPool({
            result.Name: FindAurUpdatesTask(
                package_versions=package_versions,
                result=result
            ) for result in aur_pkgs_info
        }).execute().values()
        if update
    ]
    return aur_updates, not_found_aur_pkgs
