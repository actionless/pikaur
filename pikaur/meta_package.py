from .core import (
    DataType,
    SingleTaskExecutor,
    compare_versions,
    get_package_name_and_version_matcher_from_depend_line,
    DependencyVersionMismatch,
)
from .pacman import (
    PacmanTaskWorker, PackageDB, find_local_packages, find_repo_packages,
)
from .aur import find_aur_packages


class PackageUpdate(DataType):
    Name = None
    Current_Version = None
    New_Version = None
    Description = None

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
        if compare_versions(current_version, aur_version):
            aur_update = PackageUpdate(
                Name=pkg_name,
                New_Version=aur_version,
                Current_Version=current_version,
                Description=result.Description
            )
            aur_updates.append(aur_update)
    return aur_updates, not_found_aur_pkgs


class PackagesNotFoundInAUR(DataType, Exception):
    packages = None
    wanted_by = None


def find_aur_deps(package_names):

    # @TODO: split to smaller routines

    def _get_deps_and_version_matchers(result):
        deps = {}
        for dep in (result.Depends or []) + (result.MakeDepends or []):
            name, version_matcher = get_package_name_and_version_matcher_from_depend_line(dep)
            deps[name] = version_matcher
        return deps

    all_repo_pkgs_info = PackageDB.get_repo_dict()
    all_local_pkgs_info = PackageDB.get_local_dict()
    new_aur_deps = []
    while package_names:

        all_deps_for_aur_packages = {}
        aur_pkgs_info, not_found_aur_pkgs = find_aur_packages(package_names)
        if not_found_aur_pkgs:
            raise PackagesNotFoundInAUR(packages=not_found_aur_pkgs)
        for result in aur_pkgs_info:
            all_deps_for_aur_packages.update(_get_deps_and_version_matchers(result))

        not_found_local_pkgs = []
        if all_deps_for_aur_packages:

            repo_deps_names, not_found_deps = find_repo_packages(
                all_deps_for_aur_packages.keys()
            )
            # pkgs provided by repo pkgs
            provided_by_repo_backreferences = {}
            if not_found_deps:
                repo_provided_dict = PackageDB.get_repo_provided_dict()
                for repo_pkg_name, repo_provided in repo_provided_dict.items():
                    for dep_name in not_found_deps[:]:
                        if dep_name in repo_provided:
                            not_found_deps.remove(dep_name)
                            repo_deps_names.append(dep_name)
                            provided_by_repo_backreferences.setdefault(
                                dep_name, []
                            ).append(repo_pkg_name)
            # check versions of repo packages:
            for repo_dep_name in repo_deps_names:
                version_matcher = all_deps_for_aur_packages[repo_dep_name]
                repo_pkg_infos = [
                    rpkgi for rpkgi in [
                        all_repo_pkgs_info.get(repo_dep_name)
                    ] + provided_by_repo_backreferences.get(repo_dep_name, [])
                    if rpkgi is not None
                ]
                for repo_pkg_info in repo_pkg_infos:
                    if not version_matcher(repo_pkg_info.Version):
                        raise DependencyVersionMismatch(
                            version_found=repo_pkg_info.Version,
                            dependency_line=version_matcher.line
                        )

            if not_found_deps:
                _local_pkgs_info, not_found_local_pkgs = \
                    find_local_packages(
                        not_found_deps
                    )

                # pkgs provided by local pkgs
                local_deps_names = []
                provided_by_local_backreferences = {}
                if not_found_local_pkgs:
                    local_provided_dict = PackageDB.get_local_provided_dict()
                    for local_pkg_name, local_provided in local_provided_dict.items():
                        for dep_name in not_found_local_pkgs[:]:
                            if dep_name in local_provided:
                                not_found_local_pkgs.remove(dep_name)
                                local_deps_names.append(dep_name)
                                provided_by_local_backreferences.setdefault(
                                    dep_name, []
                                ).append(local_pkg_name)
                # check versions of local packages:
                for local_dep_name in local_deps_names:
                    version_matcher = all_deps_for_aur_packages[local_dep_name]
                    # print(all_local_pkgs_info[local_dep_name])
                    local_pkg_infos = [
                        lpkgi for lpkgi in [
                            all_local_pkgs_info.get(local_dep_name)
                        ] + provided_by_local_backreferences.get(local_dep_name, [])
                        if lpkgi is not None
                    ]
                    for local_pkg_info in local_pkg_infos:
                        if not version_matcher(local_pkg_info.Version):
                            raise DependencyVersionMismatch(
                                version_found=local_pkg_info.Version,
                                dependency_line=version_matcher.line
                            )

                # try finding those packages in AUR
                aur_deps_info, not_found_aur_deps = find_aur_packages(
                    not_found_local_pkgs
                )
                # check versions of found AUR packages:
                for aur_dep_info in aur_deps_info:
                    aur_dep_name = aur_dep_info.Name
                    version_matcher = all_deps_for_aur_packages[aur_dep_name]
                    # print(aur_dep_info)
                    if not version_matcher(aur_dep_info.Version):
                        raise DependencyVersionMismatch(
                            version_found=aur_dep_info.Version,
                            dependency_line=version_matcher.line
                        )

                if not_found_aur_deps:
                    problem_packages_names = []
                    for result in aur_pkgs_info:
                        deps = _get_deps_and_version_matchers(result).keys()
                        for not_found_pkg in not_found_aur_deps:
                            if not_found_pkg in deps:
                                problem_packages_names.append(result.Name)
                                break
                    raise PackagesNotFoundInAUR(
                        packages=not_found_aur_deps,
                        wanted_by=problem_packages_names
                    )
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
            return aur_packages[0].Version
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
        if conflicts:
            new_pkgs_conflicts_lists[repo_package_name] = list(set(conflicts))
    #
    # print(conflicts)
    aur_pkgs_info, _not_founds_pkgs = find_aur_packages(aur_packages_names)
    for aur_json in aur_pkgs_info:
        conflicts = []
        conflicts += aur_json.Conflicts or []
        conflicts += aur_json.Replaces or []
        new_pkgs_conflicts_lists[aur_json.Name] = list(set(conflicts))

    all_local_pkgs_info = PackageDB.get_local_dict()
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
    all_local_pkgs_names = list(all_local_pkgs_info.keys())
    for new_pkg_name, new_pkg_conflicts_list in new_pkgs_conflicts_lists.items():
        # print(new_pkg_name)

        # find if any of new packages have Conflicts with
        # already installed ones or with each other:
        for conflict_line in new_pkg_conflicts_list:
            # print(conflict_line)
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
                        new_pkg_name != conflict_pkg_name
                    ) and (
                        conflict_version_matcher(get_version(installed_pkg_name))
                    ):
                        new_pkgs_conflicts.setdefault(new_pkg_name, []).append(conflict_pkg_name)
                for installed_pkg_name, provides in local_provided.items():
                    for provided_pkg_name in provides:
                        if (
                                conflict_pkg_name == provided_pkg_name
                        ) and (
                            new_pkg_name != installed_pkg_name
                        ) and (
                            conflict_version_matcher(get_version(installed_pkg_name))
                        ):
                            new_pkgs_conflicts.setdefault(new_pkg_name, []).append(
                                installed_pkg_name
                            )

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
                    local_pkg_name != new_pkg_name
                ) and (
                    conflict_version_matcher(get_version(new_pkg_name))
                ):
                    new_pkgs_conflicts.setdefault(new_pkg_name, []).append(local_pkg_name)
    # print(new_pkgs_conflicts)

    return new_pkgs_conflicts


def check_replacements():
    all_repo_pkgs_info = PackageDB.get_repo_dict()
    all_local_pkgs_info = PackageDB.get_local_dict()
    all_local_pkgs_names = all_local_pkgs_info.keys()

    replaces_lists = {}
    for repo_pkg_name, repo_pkg_info in all_repo_pkgs_info.items():
        if repo_pkg_info.Replaces:
            for dep_name in repo_pkg_info.Replaces:
                if dep_name != repo_pkg_name:
                    replaces_lists.setdefault(repo_pkg_name, []).append(dep_name)
    #
    new_pkgs_replaces = {}
    for pkg_name, replace_list in replaces_lists.items():
        for replace_pkg_name in replace_list:
            if replace_pkg_name in all_local_pkgs_names:
                new_pkgs_replaces.setdefault(pkg_name, []).append(replace_pkg_name)
    return new_pkgs_replaces
