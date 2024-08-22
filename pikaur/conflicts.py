"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

from typing import TYPE_CHECKING

from .aur_deps import find_repo_deps_of_aur_pkgs
from .pacman import PackageDB
from .updates import get_remote_package_version
from .version import VersionMatcher

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .pikatypes import AURInstallInfo, AURPackageInfo


def get_new_repo_pkgs_conflicts(repo_packages: list[str]) -> dict[str, list[str]]:
    new_pkgs_conflicts_lists = {}
    for repo_package_name in repo_packages:
        repo_pkg = PackageDB.find_repo_package(repo_package_name)
        conflicts: list[str] = []
        if repo_pkg.conflicts:
            conflicts += repo_pkg.conflicts
        if repo_pkg.replaces:
            conflicts += repo_pkg.replaces
        if conflicts:
            new_pkgs_conflicts_lists[repo_package_name] = list(set(conflicts))
    return new_pkgs_conflicts_lists


def get_new_aur_pkgs_conflicts(aur_packages: "list[AURPackageInfo]") -> dict[str, list[str]]:
    new_pkgs_conflicts_lists = {}
    for aur_json in aur_packages:
        conflicts: list[str] = []
        conflicts += aur_json.conflicts or []
        conflicts += aur_json.replaces or []
        new_pkgs_conflicts_lists[aur_json.name] = list(set(conflicts))
    return new_pkgs_conflicts_lists


def get_all_local_pkgs_conflicts() -> dict[str, list[str]]:
    all_local_pkgs_info = PackageDB.get_local_dict()
    all_local_pgks_conflicts_lists = {}
    for local_pkg_info in all_local_pkgs_info.values():
        conflicts: list[str] = []
        if local_pkg_info.conflicts:
            conflicts += local_pkg_info.conflicts
        if local_pkg_info.replaces:
            conflicts += local_pkg_info.replaces
        if conflicts:
            all_local_pgks_conflicts_lists[local_pkg_info.name] = list(set(conflicts))
    return all_local_pgks_conflicts_lists


def find_conflicting_with_new_pkgs(
        new_pkg_name: str,
        all_pkgs_names: list[str],
        new_pkg_conflicts_list: list[str],
) -> dict[str, list[str]]:
    """
    find if any of new packages have Conflicts with
    already installed ones or with each other
    """
    local_provided = PackageDB.get_local_provided_dict()
    new_pkgs_conflicts: dict[str, list[str]] = {}
    for conflict_line in new_pkg_conflicts_list:  # noqa: PLR1702:
        conflict_version_matcher = VersionMatcher(conflict_line, is_pkg_deps=True)
        conflict_pkg_name = conflict_version_matcher.pkg_name
        if new_pkg_name != conflict_pkg_name:
            for installed_pkg_name in all_pkgs_names:
                if (
                        conflict_pkg_name == installed_pkg_name
                ) and (
                    not conflict_version_matcher or
                    conflict_version_matcher(get_remote_package_version(installed_pkg_name))
                ):
                    new_pkgs_conflicts.setdefault(new_pkg_name, []).append(conflict_pkg_name)
            for provided_dep, provides in local_provided.items():
                for provided_pkg in provides:
                    installed_pkg_name = provided_pkg.package.name
                    if (
                            conflict_pkg_name == provided_dep
                    ) and (
                        new_pkg_name != installed_pkg_name
                    ) and (
                        not conflict_version_matcher or
                        conflict_version_matcher(
                            provided_pkg.version_matcher.version or
                            get_remote_package_version(installed_pkg_name),
                        )
                    ):
                        new_pkgs_conflicts.setdefault(new_pkg_name, [])
                        new_pkg_conflicts = new_pkgs_conflicts[new_pkg_name]
                        if installed_pkg_name not in new_pkg_conflicts:
                            new_pkg_conflicts.append(installed_pkg_name)
    return new_pkgs_conflicts


def find_conflicting_with_local_pkgs(
        new_pkg_name: str,
        all_local_pgks_conflicts_lists: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Find if any of already installed packages have Conflicts with the new ones."""
    new_pkgs_conflicts: dict[str, list[str]] = {}
    for local_pkg_name, local_pkg_conflicts_list in all_local_pgks_conflicts_lists.items():
        if new_pkg_name == local_pkg_name:
            continue
        for conflict_line in local_pkg_conflicts_list:
            conflict_version_matcher = VersionMatcher(conflict_line, is_pkg_deps=True)
            if (
                    conflict_version_matcher.pkg_name == new_pkg_name
            ) and (
                local_pkg_name != new_pkg_name
            ) and (
                conflict_version_matcher(get_remote_package_version(new_pkg_name))
            ):
                new_pkgs_conflicts.setdefault(new_pkg_name, []).append(local_pkg_name)
    return new_pkgs_conflicts


def find_aur_conflicts(
        aur_pkgs_install_infos: "Sequence[AURInstallInfo]",
        repo_packages_names: list[str],
        skip_checkdeps_for_pkgnames: list[str],
) -> dict[str, list[str]]:
    aur_pkgs: list[AURPackageInfo] = [ii.package for ii in aur_pkgs_install_infos]
    aur_packages_names = [ii.name for ii in aur_pkgs_install_infos]
    repo_deps_version_matchers = find_repo_deps_of_aur_pkgs(
        aur_pkgs, skip_checkdeps_for_pkgnames=skip_checkdeps_for_pkgnames,
    )
    repo_deps_names = [vm.pkg_name for vm in repo_deps_version_matchers]
    all_pkgs_to_be_installed = aur_packages_names + repo_deps_names

    all_local_pkgs_info = PackageDB.get_local_dict()
    all_local_pkgs_names = list(all_local_pkgs_info.keys())

    new_pkgs_conflicts_lists = {}
    new_pkgs_conflicts_lists.update(
        get_new_repo_pkgs_conflicts(repo_deps_names),
    )
    new_pkgs_conflicts_lists.update(
        get_new_aur_pkgs_conflicts(aur_pkgs),
    )
    all_local_pgks_conflicts_lists = get_all_local_pkgs_conflicts()

    conflicts_result = {}
    for new_pkg_name, new_pkg_conflicts_list in new_pkgs_conflicts_lists.items():
        conflicts_result.update(
            find_conflicting_with_new_pkgs(
                new_pkg_name,
                all_local_pkgs_names + all_pkgs_to_be_installed + repo_packages_names,
                new_pkg_conflicts_list,
            ),
        )
    for new_pkg_name in all_pkgs_to_be_installed:
        conflicts_result.update(
            find_conflicting_with_local_pkgs(new_pkg_name, all_local_pgks_conflicts_lists),
        )

    return conflicts_result
