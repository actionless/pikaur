from typing import List, Dict, Iterable

import pyalpm

from .pacman import (
    PackageDB, ProvidedDependency,
    find_local_packages, find_repo_packages,
)
from .version import (
    VersionMatcher,
    get_package_name_and_version_matcher_from_depend_line,
)
from .aur import AURPackageInfo, find_aur_packages
from .exceptions import PackagesNotFoundInAUR, DependencyVersionMismatch
from .core import PackageSource


def find_provided_pkgs(
        pkg_names: List[str],
        source: PackageSource
) -> Dict[str, List[ProvidedDependency]]:

    provided_by_backrefs: Dict[str, List[ProvidedDependency]] = {}
    if not pkg_names:
        return provided_by_backrefs
    if source == PackageSource.REPO:
        provided_dict = PackageDB.get_repo_provided_dict()
    else:
        provided_dict = PackageDB.get_local_provided_dict()
    for provided_name, provided in provided_dict.items():
        for provided_pkg in provided:
            for dep_name in pkg_names:
                if dep_name == provided_name:
                    provided_by_backrefs.setdefault(
                        dep_name, []
                    ).append(provided_pkg)
    return provided_by_backrefs


def check_deps_versions(
        aur_pkg_name: str,
        deps_pkg_names: Iterable[str],
        version_matchers: Dict[str, VersionMatcher],
        source: PackageSource
) -> List[str]:
    # try to find explicit pkgs:
    not_found_deps = None
    deps: List[pyalpm.Package] = []
    if source == PackageSource.REPO:
        deps, not_found_deps = find_repo_packages(deps_pkg_names)
    else:
        deps, not_found_deps = find_local_packages(deps_pkg_names)

    # try to find pkgs provided by other pkgs:
    provided_by_backrefs = find_provided_pkgs(
        pkg_names=not_found_deps,
        source=source
    )
    for dep_name in provided_by_backrefs:
        not_found_deps.remove(dep_name)

    # check versions of found excplicit deps:
    for dep in deps:
        dep_name = dep.name
        version_matcher = version_matchers[dep_name]
        if not version_matcher(dep.version):
            raise DependencyVersionMismatch(
                version_found=dep.version,
                dependency_line=version_matcher.line,
                who_depends=aur_pkg_name,
                depends_on=dep_name,
                location=source,
            )

    # dep via provided pkg:
    for dep_name, provided_by_pkgs in provided_by_backrefs.items():
        version_matcher = version_matchers[dep_name]
        if not sum([
                version_matcher(provided.version_matcher.version or provided.package.version)
                for provided in provided_by_pkgs
        ]):
            raise DependencyVersionMismatch(
                version_found={
                    provided.name: provided.package.version for provided in provided_by_pkgs
                },
                dependency_line=version_matcher.line,
                who_depends=aur_pkg_name,
                depends_on=dep_name,
                location=source,
            )

    return not_found_deps


def get_aur_pkg_deps_and_version_matchers(aur_pkg: AURPackageInfo) -> Dict[str, VersionMatcher]:
    deps = {}
    for dep in (aur_pkg.depends or []) + (aur_pkg.makedepends or []):
        name, version_matcher = get_package_name_and_version_matcher_from_depend_line(dep)
        deps[name] = version_matcher
    return deps


def find_missing_deps_for_aur_pkg(
        aur_pkg_name: str,
        version_matchers: Dict[str, VersionMatcher],
        aur_pkgs_info: List[AURPackageInfo]
) -> List[str]:
    # repo pkgs
    not_found_deps = check_deps_versions(
        aur_pkg_name=aur_pkg_name,
        deps_pkg_names=version_matchers.keys(),
        version_matchers=version_matchers,
        source=PackageSource.REPO
    )

    if not not_found_deps:
        return []

    # local pkgs
    not_found_local_pkgs = check_deps_versions(
        aur_pkg_name=aur_pkg_name,
        deps_pkg_names=not_found_deps,
        version_matchers=version_matchers,
        source=PackageSource.LOCAL
    )
    if not not_found_local_pkgs:
        return []

    # try finding those packages in AUR
    aur_deps_info, not_found_aur_deps = find_aur_packages(
        not_found_local_pkgs
    )
    # @TODO: find packages Provided by AUR packages
    if not_found_aur_deps:
        problem_packages_names = []
        for result in aur_pkgs_info:
            deps = get_aur_pkg_deps_and_version_matchers(result).keys()
            for not_found_pkg in not_found_aur_deps:
                if not_found_pkg in deps:
                    problem_packages_names.append(result.name)
                    break
        raise PackagesNotFoundInAUR(
            packages=not_found_aur_deps,
            wanted_by=problem_packages_names
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
    return not_found_local_pkgs


def find_aur_deps(package_names: List[str]) -> Dict[str, List[str]]:
    new_aur_deps: List[str] = []
    result_aur_deps: Dict[str, List[str]] = {}

    iter_package_names = package_names[:]
    while iter_package_names:
        all_deps_for_aur_packages = {}
        aur_pkgs_info, not_found_aur_pkgs = find_aur_packages(iter_package_names)
        if not_found_aur_pkgs:
            raise PackagesNotFoundInAUR(packages=not_found_aur_pkgs)
        for aur_pkg in aur_pkgs_info:
            aur_pkg_deps = get_aur_pkg_deps_and_version_matchers(aur_pkg)
            if aur_pkg_deps:
                all_deps_for_aur_packages[aur_pkg.name] = aur_pkg_deps

        not_found_local_pkgs: List[str] = []
        for aur_pkg_name, deps_for_aur_package in all_deps_for_aur_packages.items():
            non_local_pkgs = find_missing_deps_for_aur_pkg(
                aur_pkg_name=aur_pkg_name,
                aur_pkgs_info=aur_pkgs_info,
                version_matchers=deps_for_aur_package,
            )
            not_found_local_pkgs += non_local_pkgs
            for dep_pkg_name in non_local_pkgs:
                result_aur_deps.setdefault(aur_pkg_name, []).append(dep_pkg_name)
        iter_package_names = []
        for pkg_name in not_found_local_pkgs:
            if pkg_name not in new_aur_deps and pkg_name not in package_names:
                new_aur_deps.append(pkg_name)
                iter_package_names.append(pkg_name)

    return result_aur_deps
