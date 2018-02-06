import sys

from .core import (
    DataType,
    SingleTaskExecutor,
    compare_versions, get_package_name_from_depend_line,
)
from .pacman import (
    PacmanTaskWorker, PackageDB, find_local_packages, find_repo_packages,
)
from .aur import find_aur_packages

from .pprint import print_not_found_packages, color_line, bold_line


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


def find_aur_deps(package_names):

    # @TODO: split to smaller routines

    def _get_deps(result):
        return [
            get_package_name_from_depend_line(dep) for dep in
            result.get('Depends', []) + result.get('MakeDepends', [])
        ]

    new_aur_deps = []
    while package_names:

        all_deps_for_aur_packages = []
        aur_pkgs_info, not_found_aur_pkgs = find_aur_packages(package_names)
        if not_found_aur_pkgs:
            print_not_found_packages(not_found_aur_pkgs)
            sys.exit(1)
        for result in aur_pkgs_info:
            all_deps_for_aur_packages += _get_deps(result)
        all_deps_for_aur_packages = list(set(all_deps_for_aur_packages))

        not_found_local_pkgs = []
        if all_deps_for_aur_packages:
            _, not_found_deps = find_repo_packages(
                all_deps_for_aur_packages
            )

            # pkgs provided by repo pkgs
            if not_found_deps:
                repo_provided = PackageDB.get_repo_provided()
                for dep_name in not_found_deps[:]:
                    if dep_name in repo_provided:
                        not_found_deps.remove(dep_name)

            if not_found_deps:
                _local_pkgs_info, not_found_local_pkgs = \
                    find_local_packages(
                        not_found_deps
                    )

                # pkgs provided by repo pkgs
                if not_found_local_pkgs:
                    local_provided = PackageDB.get_local_provided()
                    for dep_name in not_found_local_pkgs[:]:
                        if dep_name in local_provided:
                            not_found_local_pkgs.remove(dep_name)

                # try finding those packages in AUR
                _aur_deps_info, not_found_aur_deps = find_aur_packages(
                    not_found_local_pkgs
                )
                if not_found_aur_deps:
                    problem_package_names = []
                    for result in aur_pkgs_info:
                        deps = _get_deps(result)
                        for not_found_pkg in not_found_aur_deps:
                            if not_found_pkg in deps:
                                problem_package_names.append(result['Name'])
                                break
                    print("{} {}".format(
                        color_line(':: error:', 9),
                        bold_line(
                            'Dependencies missing for '
                            f'{problem_package_names}'
                        ),
                    ))
                    print_not_found_packages(not_found_aur_deps)
                    sys.exit(1)
        new_aur_deps += not_found_local_pkgs
        package_names = not_found_local_pkgs

    return list(set(new_aur_deps))


def check_conflicts(repo_packages_names, aur_packages_names):

    # @TODO: split to smaller routines (?)

    def clean_conflicts_list(conflicts):
        return list(set([
            get_package_name_from_depend_line(pkg_name)
            for pkg_name in conflicts
        ]))

    new_pkgs_conflicts_lists = {}
    #
    all_repo_pkgs_info = PackageDB.get_repo_dict()
    for repo_package_name in repo_packages_names:
        repo_pkg_info = all_repo_pkgs_info[repo_package_name]
        conflicts = []
        if repo_pkg_info.Conflicts_With:
            conflicts += repo_pkg_info.Conflicts_With
        if repo_pkg_info.Replaces:
            conflicts += repo_pkg_info.Replaces
        new_pkgs_conflicts_lists[repo_package_name] = clean_conflicts_list(
            conflicts
        )
    #
    aur_pkgs_info, _not_founds_pkgs = find_aur_packages(aur_packages_names)
    for aur_json in aur_pkgs_info:
        conflicts = []
        conflicts += aur_json.get('Conflicts', [])
        conflicts += aur_json.get('Replaces', [])
        new_pkgs_conflicts_lists[aur_json['Name']] = clean_conflicts_list(
            conflicts
        )
    # print(new_pkgs_conflicts_lists)

    all_local_pkgs_info = PackageDB.get_local_dict()
    all_local_pkgs_names = all_local_pkgs_info.keys()
    all_local_pgks_conflicts_lists = {}
    for local_pkg_info in all_local_pkgs_info.values():
        conflicts = []
        if local_pkg_info.Conflicts_With:
            conflicts += local_pkg_info.Conflicts_With
        if local_pkg_info.Replaces:
            conflicts += local_pkg_info.Replaces
        if conflicts:
            all_local_pgks_conflicts_lists[local_pkg_info.Name] = clean_conflicts_list(
                conflicts
            )
    # print(all_local_pgks_conflicts_lists)

    new_pkgs_conflicts = {}
    for new_pkg_name, new_pkg_conflicts_list in new_pkgs_conflicts_lists.items():

        for conflict_pkg_name in new_pkg_conflicts_list:
            if new_pkg_name != conflict_pkg_name and conflict_pkg_name in (
                    list(all_local_pkgs_names) + list(new_pkgs_conflicts_lists.keys())
            ):
                new_pkgs_conflicts.setdefault(new_pkg_name, []).append(conflict_pkg_name)

        for local_pkg_name, local_pkg_conflicts_list in (
                list(all_local_pgks_conflicts_lists.items()) +
                list(new_pkgs_conflicts_lists.items())
        ):
            if new_pkg_name == local_pkg_name:
                continue
            for conflict_pkg_name in new_pkg_conflicts_list + [new_pkg_name]:
                if conflict_pkg_name in local_pkg_conflicts_list:
                    new_pkgs_conflicts.setdefault(new_pkg_name, []).append(local_pkg_name)
    # print(new_pkgs_conflicts)

    return new_pkgs_conflicts
