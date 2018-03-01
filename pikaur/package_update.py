from .core import DataType
from .version import compare_versions
from .pacman import PackageDB, find_packages_not_from_repo
from .aur import find_aur_packages
from .pprint import print_status_message


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
    repo_packages_updates = []
    repo_dict = PackageDB.get_repo_dict()
    for local_pkg in PackageDB.get_local_list():
        repo_pkg = repo_dict.get(local_pkg.name)
        if not repo_pkg:
            continue
        if compare_versions(local_pkg.version, repo_pkg.version) < 0:
            repo_packages_updates.append(
                PackageUpdate(
                    Name=local_pkg.name,
                    New_Version=repo_pkg.version,
                    Current_Version=local_pkg.version,
                    Description=repo_pkg.desc,
                )
            )
    return repo_packages_updates


def find_aur_updates():
    package_names = find_packages_not_from_repo()
    local_packages = PackageDB.get_local_dict()
    print_status_message("Reading AUR packages info...")
    aur_pkgs_info, not_found_aur_pkgs = find_aur_packages(package_names)
    aur_updates = []
    for result in aur_pkgs_info:
        pkg_name = result.name
        aur_version = result.version
        current_version = local_packages[pkg_name].version
        compare_result = compare_versions(current_version, aur_version)
        if compare_result < 0:
            aur_updates.append(PackageUpdate(
                Name=pkg_name,
                New_Version=aur_version,
                Current_Version=current_version,
                Description=result.desc
            ))
    return aur_updates, not_found_aur_pkgs


def get_remote_package_version(new_pkg_name):
    repo_info = PackageDB.get_repo_dict().get(new_pkg_name)
    if repo_info:
        return repo_info.version
    aur_packages, _not_found = find_aur_packages([new_pkg_name])
    if aur_packages:
        return aur_packages[0].version
    return None
