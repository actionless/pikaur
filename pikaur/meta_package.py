import sys

from .core import (
    DataType,
    SingleTaskExecutor,
    compare_versions,
    get_package_name_from_depend_line,
    get_package_name_and_version_matcher_from_depend_line,
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

    def __repr__(self):
        return f'<{self.__class__.__name__} "{self.Name}" {self.Current_Version} -> {self.New_Version}>'


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

    def get_version(new_pkg_name):
        repo_info = PackageDB.get_repo_dict().get(new_pkg_name)
        if repo_info:
            return repo_info.Version
        aur_packages, _not_found = find_aur_packages([new_pkg_name])
        if aur_packages:
            return aur_packages[0]['Version']
        return None

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
        new_pkgs_conflicts_lists[repo_package_name] = list(set(conflicts))
    #
    aur_pkgs_info, _not_founds_pkgs = find_aur_packages(aur_packages_names)
    for aur_json in aur_pkgs_info:
        conflicts = []
        conflicts += aur_json.get('Conflicts', [])
        conflicts += aur_json.get('Replaces', [])
        new_pkgs_conflicts_lists[aur_json['Name']] = list(set(conflicts))
    # print(new_pkgs_conflicts_lists)

    all_local_pkgs_info = PackageDB.get_local_dict()
    all_local_pkgs_names = list(all_local_pkgs_info.keys())
    all_local_pgks_conflicts_lists = {}
    for local_pkg_info in all_local_pkgs_info.values():
        conflicts = []
        if local_pkg_info.Conflicts_With:
            conflicts += local_pkg_info.Conflicts_With
        if local_pkg_info.Replaces:
            conflicts += local_pkg_info.Replaces
        if conflicts:
            all_local_pgks_conflicts_lists[local_pkg_info.Name] = list(set(conflicts))
    # print(all_local_pgks_conflicts_lists)

    new_pkgs_conflicts = {}
    local_provided = PackageDB.get_local_provided_dict()
    all_new_pkgs_names = repo_packages_names + aur_packages_names
    for new_pkg_name, new_pkg_conflicts_list in new_pkgs_conflicts_lists.items():

        # find if any of new packages have Conflicts with
        # already installed ones or with each other:
        for conflict_line in new_pkg_conflicts_list:
            conflict_pkg_name, conflict_version_matcher = \
                get_package_name_and_version_matcher_from_depend_line(
                    conflict_line
                )
            if new_pkg_name != conflict_pkg_name:
                for installed_pkg_name in (
                        all_local_pkgs_names + all_new_pkgs_names
                ):
                    if (
                            conflict_pkg_name == installed_pkg_name
                    ) and (
                        conflict_version_matcher(get_version(installed_pkg_name))
                    ):
                        new_pkgs_conflicts.setdefault(new_pkg_name, []).append(conflict_pkg_name)
                for installed_pkg_name, provides in local_provided.items():
                    for provided_pkg_name in provides:
                        if (
                                conflict_pkg_name == provided_pkg_name
                        ) and (
                            conflict_version_matcher(get_version(installed_pkg_name))
                        ):
                            new_pkgs_conflicts.setdefault(new_pkg_name, []).append(installed_pkg_name)

        # find if any of already installed packages have Conflicts with the new ones:
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
                    conflict_version_matcher(get_version(new_pkg_name))
                ):
                    new_pkgs_conflicts.setdefault(new_pkg_name, []).append(local_pkg_name)
    # print(new_pkgs_conflicts)

    return new_pkgs_conflicts
