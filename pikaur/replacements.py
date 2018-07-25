from typing import List, Dict

from .i18n import _n
from .pacman import PackageDB
from .exceptions import PackagesNotFoundInRepo
from .pprint import print_warning


def find_replacements() -> Dict[str, List[str]]:
    all_repo_pkgs_info = PackageDB.get_repo_list()
    all_repo_pkg_names = PackageDB.get_repo_pkgnames()
    all_local_pkgs_info = PackageDB.get_local_dict()
    all_local_pkgs_names = all_local_pkgs_info.keys()

    replaces_lists: Dict[str, List[str]] = {}
    for repo_pkg_info in all_repo_pkgs_info:
        if repo_pkg_info.replaces:
            for dep_name in repo_pkg_info.replaces:
                repo_pkg_name = repo_pkg_info.name
                if dep_name != repo_pkg_name:
                    replaces_lists.setdefault(repo_pkg_name, []).append(dep_name)

    new_pkgs_replaces: Dict[str, List[str]] = {}
    for pkg_name, replace_list in replaces_lists.items():
        for replace_pkg_name in replace_list:
            try:
                if (replace_pkg_name in all_local_pkgs_names) and (
                        (pkg_name not in all_repo_pkg_names) or (
                            replace_pkg_name not in all_repo_pkg_names or (
                                PackageDB.get_repo_priority(
                                    PackageDB.find_repo_package(replace_pkg_name).db.name
                                ) >= PackageDB.get_repo_priority(
                                    PackageDB.find_repo_package(pkg_name).db.name
                                )
                            )
                        )
                ):
                    new_pkgs_replaces.setdefault(pkg_name, []).append(replace_pkg_name)
            except PackagesNotFoundInRepo as exc:
                print_warning(
                    _n(
                        "'{packages}' package is available in the repo but can't be installed",
                        "'{packages}' packages are available in the repo but can't be installed",
                        len(exc.packages)
                    ).format(
                        packages=', '.join(exc.packages)
                    )
                )
    return new_pkgs_replaces
