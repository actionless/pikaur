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
            provided_by_repo_backrefs = {}
            if not_found_deps:
                repo_provided_dict = PackageDB.get_repo_provided_dict()
                for repo_pkg_name, repo_provided in repo_provided_dict.items():
                    for dep_name in not_found_deps[:]:
                        if dep_name in repo_provided:
                            not_found_deps.remove(dep_name)
                            repo_deps_names.append(dep_name)
                            provided_by_repo_backrefs.setdefault(
                                dep_name, []
                            ).append(repo_pkg_name)
            # check versions of repo packages:
            for repo_dep_name in repo_deps_names:
                version_matcher = all_deps_for_aur_packages[repo_dep_name]
                repo_pkg_infos = [
                    rpkgi for rpkgi in [
                        all_repo_pkgs_info.get(repo_dep_name)
                    ] + provided_by_repo_backrefs.get(repo_dep_name, [])
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
                provided_by_local_backrefs = {}
                if not_found_local_pkgs:
                    local_provided_dict = PackageDB.get_local_provided_dict()
                    for local_pkg_name, local_provided in local_provided_dict.items():
                        for dep_name in not_found_local_pkgs[:]:
                            if dep_name in local_provided:
                                not_found_local_pkgs.remove(dep_name)
                                local_deps_names.append(dep_name)
                                provided_by_local_backrefs.setdefault(
                                    dep_name, []
                                ).append(local_pkg_name)
                # check versions of local packages:
                for local_dep_name in local_deps_names:
                    version_matcher = all_deps_for_aur_packages[local_dep_name]
                    # print(all_local_pkgs_info[local_dep_name])
                    local_pkg_infos = [
                        lpkgi for lpkgi in [
                            all_local_pkgs_info.get(local_dep_name)
                        ] + provided_by_local_backrefs.get(local_dep_name, [])
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


def get_package_version(new_pkg_name):
    repo_info = PackageDB.get_repo_dict().get(new_pkg_name)
    if repo_info:
        return repo_info.Version
    aur_packages, _not_found = find_aur_packages([new_pkg_name])
    if aur_packages:
        return aur_packages[0].Version
    return None
