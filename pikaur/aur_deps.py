""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

from multiprocessing.pool import ThreadPool
from typing import List, Dict

from .i18n import _
from .pacman import PackageDB
from .version import VersionMatcher
from .aur import AURPackageInfo, find_aur_packages
from .exceptions import PackagesNotFoundInAUR, DependencyVersionMismatch, PackagesNotFoundInRepo
from .core import PackageSource
from .pprint import print_error


def check_deps_versions(
        deps_pkg_names: List[str],
        version_matchers: Dict[str, VersionMatcher],
        source: PackageSource
) -> List[str]:
    not_found_deps: List[str] = []
    deps_lines = [
        version_matchers[dep_name].line
        for dep_name in deps_pkg_names
    ]
    if source == PackageSource.REPO:
        not_found_deps = PackageDB.get_not_found_repo_packages(deps_lines)
    else:
        not_found_deps = PackageDB.get_not_found_local_packages(deps_lines)
    return not_found_deps


def get_aur_pkg_deps_and_version_matchers(aur_pkg: AURPackageInfo) -> Dict[str, VersionMatcher]:
    deps: Dict[str, VersionMatcher] = {}
    for dep_line in (
            (aur_pkg.depends or []) + (aur_pkg.makedepends or []) + (aur_pkg.checkdepends or [])
    ):
        version_matcher = VersionMatcher(dep_line)
        name = version_matcher.pkg_name
        if name not in deps:
            deps[name] = version_matcher
        else:
            deps[name].add_version_matcher(version_matcher)
    return deps


def handle_not_found_aur_pkgs(
        aur_pkg_name: str,
        aur_pkgs_info: List[AURPackageInfo],
        not_found_aur_deps: List[str],
) -> None:
    if not not_found_aur_deps:
        return
    all_repo_provided_packages = PackageDB.get_repo_provided_dict()
    all_local_provided_packages = PackageDB.get_local_provided_dict()

    problem_packages_names = []
    for aur_pkg in aur_pkgs_info:
        version_matchers = get_aur_pkg_deps_and_version_matchers(aur_pkg)
        deps = version_matchers.keys()
        for not_found_pkg in not_found_aur_deps:
            if not_found_pkg in deps:
                version_matcher = version_matchers[not_found_pkg]

                try:
                    failed_pkg = PackageDB.find_repo_package(not_found_pkg)
                except PackagesNotFoundInRepo:
                    pass
                else:
                    version_found = failed_pkg.version
                    if not_found_pkg in all_repo_provided_packages:
                        version_found = str({
                            provided.name: provided.package.version
                            for provided in all_repo_provided_packages[not_found_pkg]
                        })
                    raise DependencyVersionMismatch(
                        version_found=version_found,
                        dependency_line=version_matcher.line,
                        who_depends=aur_pkg_name,
                        depends_on=not_found_pkg,
                        location=PackageSource.REPO,
                    )

                not_found_local_pkgs = PackageDB.get_not_found_local_packages([not_found_pkg])
                if not not_found_local_pkgs:
                    raise DependencyVersionMismatch(
                        version_found={
                            provided.name: provided.package.version
                            for provided in all_local_provided_packages[not_found_pkg]
                        },
                        dependency_line=version_matcher.line,
                        who_depends=aur_pkg_name,
                        depends_on=not_found_pkg,
                        location=PackageSource.LOCAL,
                    )

                problem_packages_names.append(aur_pkg.name)
                break

    raise PackagesNotFoundInAUR(
        packages=not_found_aur_deps,
        wanted_by=problem_packages_names
    )


def check_requested_pkgs(
        aur_pkg_name: str,
        version_matchers: Dict[str, VersionMatcher],
        aur_pkgs_info: List[AURPackageInfo],
) -> List[str]:
    # check versions of explicitly chosen AUR packages which could be deps:
    # @TODO: also check against user-requested repo packages
    not_found_in_requested_pkgs: List[str] = list(version_matchers.keys())
    for dep_name, version_matcher in version_matchers.items():
        for aur_pkg in aur_pkgs_info:
            if dep_name not in not_found_in_requested_pkgs:
                continue
            if (
                    aur_pkg.name != dep_name
            ) and (
                not aur_pkg.provides or dep_name not in [
                    VersionMatcher(prov_line).pkg_name
                    for prov_line in aur_pkg.provides
                ]
            ):
                continue
            if not version_matcher(aur_pkg.version):
                if not aur_pkg.provides or not min([
                        version_matcher(VersionMatcher(prov_line).version)
                        for prov_line in aur_pkg.provides
                ]):
                    raise DependencyVersionMismatch(
                        version_found=aur_pkg.version,
                        dependency_line=version_matcher.line,
                        who_depends=aur_pkg_name,
                        depends_on=dep_name,
                        location=PackageSource.AUR
                    )
            not_found_in_requested_pkgs.remove(dep_name)
    return not_found_in_requested_pkgs


def find_missing_deps_for_aur_pkg(
        aur_pkg_name: str,
        version_matchers: Dict[str, VersionMatcher],
        aur_pkgs_info: List[AURPackageInfo]
) -> List[str]:

    # check if any of packages requested to install by user
    # are satisfying any of the deps:
    not_found_in_requested_pkgs = check_requested_pkgs(
        aur_pkg_name=aur_pkg_name,
        version_matchers=version_matchers,
        aur_pkgs_info=aur_pkgs_info
    )
    if not not_found_in_requested_pkgs:
        return []

    # check among local pkgs:
    not_found_local_pkgs = check_deps_versions(
        deps_pkg_names=not_found_in_requested_pkgs,
        version_matchers=version_matchers,
        source=PackageSource.LOCAL
    )
    if not not_found_local_pkgs:
        return []

    # repo pkgs:
    not_found_repo_pkgs = check_deps_versions(
        deps_pkg_names=not_found_local_pkgs,
        version_matchers=version_matchers,
        source=PackageSource.REPO
    )
    if not not_found_repo_pkgs:
        return []

    # try finding those packages in AUR
    aur_deps_info, not_found_aur_deps = find_aur_packages(
        not_found_repo_pkgs
    )
    # @TODO: find packages Provided by AUR packages
    handle_not_found_aur_pkgs(
        aur_pkg_name=aur_pkg_name,
        aur_pkgs_info=aur_pkgs_info,
        not_found_aur_deps=not_found_aur_deps,
    )

    # check versions of found AUR packages:
    for aur_dep_info in aur_deps_info:
        aur_dep_name = aur_dep_info.name
        version_matcher = version_matchers[aur_dep_name]
        # print(aur_dep_info)
        if not version_matcher(aur_dep_info.version):
            raise DependencyVersionMismatch(
                version_found=aur_dep_info.version,
                dependency_line=version_matcher.line,
                who_depends=aur_pkg_name,
                depends_on=aur_dep_name,
                location=PackageSource.AUR
            )

    return not_found_repo_pkgs


def find_aur_deps(aur_pkgs_infos: List[AURPackageInfo]) -> Dict[str, List[str]]:
    # pylint: disable=too-many-locals,too-many-branches
    new_aur_deps: List[str] = []
    package_names = [
        aur_pkg.name
        for aur_pkg in aur_pkgs_infos
    ]
    result_aur_deps: Dict[str, List[str]] = {}

    initial_pkg_infos = aur_pkgs_infos[:]
    iter_package_names: List[str] = []
    while iter_package_names or initial_pkg_infos:
        all_deps_for_aur_packages = {}
        if initial_pkg_infos:
            aur_pkgs_info = initial_pkg_infos
            not_found_aur_pkgs: List[str] = []
            initial_pkg_infos = []
        else:
            aur_pkgs_info, not_found_aur_pkgs = find_aur_packages(iter_package_names)
        if not_found_aur_pkgs:
            raise PackagesNotFoundInAUR(packages=not_found_aur_pkgs)
        for aur_pkg in aur_pkgs_info:
            aur_pkg_deps = get_aur_pkg_deps_and_version_matchers(aur_pkg)
            if aur_pkg_deps:
                all_deps_for_aur_packages[aur_pkg.name] = aur_pkg_deps

        not_found_local_pkgs: List[str] = []
        with ThreadPool() as pool:
            all_requests = {}
            for aur_pkg_name, deps_for_aur_package in all_deps_for_aur_packages.items():
                all_requests[aur_pkg_name] = pool.apply_async(
                    find_missing_deps_for_aur_pkg, (
                        aur_pkg_name,
                        deps_for_aur_package,
                        aur_pkgs_info,
                    )
                )
            pool.close()
            pool.join()
            for aur_pkg_name, request in all_requests.items():
                try:
                    results = request.get()
                except Exception as exc:
                    print_error(_(
                        "Can't resolve dependencies for AUR package '{pkg}':"
                    ).format(pkg=aur_pkg_name))
                    raise exc
                not_found_local_pkgs += results
                for dep_pkg_name in results:
                    if dep_pkg_name not in package_names:
                        result_aur_deps.setdefault(aur_pkg_name, []).append(dep_pkg_name)

        iter_package_names = []
        for pkg_name in not_found_local_pkgs:
            if pkg_name not in new_aur_deps and pkg_name not in package_names:
                new_aur_deps.append(pkg_name)
                iter_package_names.append(pkg_name)

    return result_aur_deps


def get_aur_deps_list(aur_pkgs_infos: List[AURPackageInfo]) -> List[AURPackageInfo]:
    aur_deps_relations = find_aur_deps(aur_pkgs_infos)
    all_aur_deps = list(set(
        dep
        for _pkg, deps in aur_deps_relations.items()
        for dep in deps
    ))
    return find_aur_packages(all_aur_deps)[0]


def _find_repo_deps_of_aur_pkg(
        aur_pkg: AURPackageInfo,
        all_aur_pkgs: List[AURPackageInfo]
) -> List[VersionMatcher]:
    new_deps_vms: List[VersionMatcher] = []

    version_matchers = get_aur_pkg_deps_and_version_matchers(aur_pkg)

    not_found_in_requested_pkgs = check_requested_pkgs(
        aur_pkg_name=aur_pkg.name,
        version_matchers={
            name: version_matchers[name]
            for name in PackageDB.get_not_found_local_packages(
                [vm.line for vm in version_matchers.values()]
            )
        },
        aur_pkgs_info=all_aur_pkgs
    )

    for dep_name, version_matcher in version_matchers.items():
        if dep_name not in not_found_in_requested_pkgs:
            continue
        try:
            PackageDB.find_repo_package(version_matcher.line)
        except PackagesNotFoundInRepo:
            continue
        else:
            new_deps_vms.append(version_matcher)
    return new_deps_vms


def find_repo_deps_of_aur_pkgs(aur_pkgs: List[AURPackageInfo]) -> List[VersionMatcher]:
    new_dep_names: List[VersionMatcher] = []
    with ThreadPool() as pool:
        results = [
            pool.apply_async(_find_repo_deps_of_aur_pkg, (aur_pkg, aur_pkgs, ))
            for aur_pkg in aur_pkgs
        ]
        pool.close()
        pool.join()
        for result in results:
            new_dep_names += result.get()
    return list(set(new_dep_names))
