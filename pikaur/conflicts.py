from .pacman import PackageDB
from .aur import find_aur_packages
from .version import get_package_name_and_version_matcher_from_depend_line
from .package_update import get_remote_package_version


def get_new_repo_pkgs_conflicts(repo_packages_names):
    new_pkgs_conflicts_lists = {}
    all_repo_pkgs_info = PackageDB.get_repo_dict()
    for repo_package_name in repo_packages_names:
        repo_pkg_info = all_repo_pkgs_info[repo_package_name]
        conflicts = []
        if repo_pkg_info.conflicts:
            conflicts += repo_pkg_info.conflicts
        if repo_pkg_info.replaces:
            conflicts += repo_pkg_info.replaces
        if conflicts:
            new_pkgs_conflicts_lists[repo_package_name] = list(set(conflicts))
    return new_pkgs_conflicts_lists


def get_new_aur_pkgs_conflicts(aur_packages_names):
    new_pkgs_conflicts_lists = {}
    aur_pkgs_info, _not_founds_pkgs = find_aur_packages(aur_packages_names)
    for aur_json in aur_pkgs_info:
        conflicts = []
        conflicts += aur_json.Conflicts or []
        conflicts += aur_json.Replaces or []
        new_pkgs_conflicts_lists[aur_json.Name] = list(set(conflicts))
    return new_pkgs_conflicts_lists


def get_all_local_pkgs_conflicts(all_local_pkgs_info):
    all_local_pgks_conflicts_lists = {}
    for local_pkg_info in all_local_pkgs_info.values():
        conflicts = []
        if local_pkg_info.conflicts:
            conflicts += local_pkg_info.conflicts
        if local_pkg_info.replaces:
            conflicts += local_pkg_info.replaces
        if conflicts:
            all_local_pgks_conflicts_lists[local_pkg_info.name] = list(set(conflicts))
    return all_local_pgks_conflicts_lists


def find_conflicting_with_new_pkgs(new_pkg_name, all_pkgs_names, new_pkg_conflicts_list):
    # find if any of new packages have Conflicts with
    # already installed ones or with each other:
    local_provided = PackageDB.get_local_provided_dict()
    new_pkgs_conflicts = {}
    for conflict_line in new_pkg_conflicts_list:
        conflict_pkg_name, conflict_version_matcher = \
            get_package_name_and_version_matcher_from_depend_line(
                conflict_line
            )
        if new_pkg_name != conflict_pkg_name:
            for installed_pkg_name in all_pkgs_names:
                if (
                        conflict_pkg_name == installed_pkg_name
                ) and (
                    new_pkg_name != conflict_pkg_name
                ) and (
                    conflict_version_matcher(get_remote_package_version(installed_pkg_name))
                ):
                    new_pkgs_conflicts.setdefault(new_pkg_name, []).append(conflict_pkg_name)
            for installed_pkg_name, provides in local_provided.items():
                for provided_pkg in provides:
                    if (
                            conflict_pkg_name == provided_pkg.name
                    ) and (
                        new_pkg_name != installed_pkg_name
                    ) and (
                        conflict_version_matcher(
                            provided_pkg.version_matcher.version or
                            get_remote_package_version(installed_pkg_name)
                        )
                    ):
                        new_pkgs_conflicts.setdefault(new_pkg_name, []).append(
                            installed_pkg_name
                        )
    return new_pkgs_conflicts


def find_conflicting_with_local_pkgs(new_pkg_name, all_local_pgks_conflicts_lists):
    # find if any of already installed packages have Conflicts with the new ones:
    new_pkgs_conflicts = {}
    for local_pkg_name, local_pkg_conflicts_list in all_local_pgks_conflicts_lists.items():
        if new_pkg_name == local_pkg_name:
            continue
        for conflict_line in local_pkg_conflicts_list:
            conflict_pkg_name, conflict_version_matcher = \
                get_package_name_and_version_matcher_from_depend_line(
                    conflict_line
                )
            if (
                    conflict_pkg_name == new_pkg_name
            ) and (
                local_pkg_name != new_pkg_name
            ) and (
                conflict_version_matcher(get_remote_package_version(new_pkg_name))
            ):
                new_pkgs_conflicts.setdefault(new_pkg_name, []).append(local_pkg_name)
    return new_pkgs_conflicts


def check_conflicts(repo_packages_names, aur_packages_names):
    all_local_pkgs_info = PackageDB.get_local_dict()
    all_local_pkgs_names = list(all_local_pkgs_info.keys())
    all_new_pkgs_names = repo_packages_names + aur_packages_names

    new_pkgs_conflicts_lists = {}
    new_pkgs_conflicts_lists.update(
        get_new_repo_pkgs_conflicts(repo_packages_names)
    )
    new_pkgs_conflicts_lists.update(
        get_new_aur_pkgs_conflicts(aur_packages_names)
    )
    all_local_pgks_conflicts_lists = get_all_local_pkgs_conflicts(
        all_local_pkgs_info
    )

    conflicts_result = {}
    for new_pkg_name, new_pkg_conflicts_list in new_pkgs_conflicts_lists.items():
        conflicts_result.update(
            find_conflicting_with_new_pkgs(
                new_pkg_name,
                all_local_pkgs_names + all_new_pkgs_names,
                new_pkg_conflicts_list
            )
        )
    for new_pkg_name in all_new_pkgs_names:
        conflicts_result.update(
            find_conflicting_with_local_pkgs(new_pkg_name, all_local_pgks_conflicts_lists)
        )

    return conflicts_result


def check_replacements():
    all_repo_pkgs_info = PackageDB.get_repo_dict()
    all_local_pkgs_info = PackageDB.get_local_dict()
    all_local_pkgs_names = all_local_pkgs_info.keys()

    replaces_lists = {}
    for repo_pkg_name, repo_pkg_info in all_repo_pkgs_info.items():
        if repo_pkg_info.replaces:
            for dep_name in repo_pkg_info.replaces:
                if dep_name != repo_pkg_name:
                    replaces_lists.setdefault(repo_pkg_name, []).append(dep_name)

    new_pkgs_replaces = {}
    for pkg_name, replace_list in replaces_lists.items():
        for replace_pkg_name in replace_list:
            if replace_pkg_name in all_local_pkgs_names:
                new_pkgs_replaces.setdefault(pkg_name, []).append(replace_pkg_name)
    return new_pkgs_replaces
