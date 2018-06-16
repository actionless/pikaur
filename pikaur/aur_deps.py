from typing import List, Dict

import pyalpm

from .pacman import (
    PackageDB, ProvidedDependency,
    find_local_packages,
)
from .version import (
    VersionMatcher,
    get_package_name_and_version_matcher_from_depend_line,
)
from .aur import AURPackageInfo, find_aur_packages
from .exceptions import PackagesNotFoundInAUR, DependencyVersionMismatch, PackagesNotFoundInRepo
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


def check_deps_versions(  # pylint:disable=too-many-branches
        aur_pkg_name: str,
        deps_pkg_names: List[str],
        version_matchers: Dict[str, VersionMatcher],
        source: PackageSource
) -> List[str]:
    # try to find explicit pkgs:
    not_found_deps = []
    deps: Dict[str, pyalpm.Package] = {}
    if source == PackageSource.REPO:
        for dep_name in deps_pkg_names:
            try:
                result = PackageDB.find_repo_package(dep_name)
            except PackagesNotFoundInRepo:
                not_found_deps.append(dep_name)
            else:
                deps[dep_name] = result
    else:
        deps_list, not_found_deps = find_local_packages(deps_pkg_names)
        deps = {dep.name: dep for dep in deps_list}

    # try to find pkgs provided by other pkgs:
    provided_by_backrefs = find_provided_pkgs(
        pkg_names=deps_pkg_names,
        source=source
    )
    for dep_name in provided_by_backrefs:
        if dep_name in not_found_deps:
            not_found_deps.remove(dep_name)
        if dep_name in deps:
            del deps[dep_name]

    # check versions of found excplicit deps:
    for dep_name, dep in list(deps.items())[:]:
        version_matcher = version_matchers[dep_name]
        if not version_matcher(dep.version):
            if source == PackageSource.REPO:
                raise DependencyVersionMismatch(
                    version_found=dep.version,
                    dependency_line=version_matcher.line,
                    who_depends=aur_pkg_name,
                    depends_on=dep_name,
                    location=source,
                )
            else:
                del deps[dep_name]
                not_found_deps.append(dep_name)

    # dep via provided pkg:
    for dep_name, provided_by_pkgs in provided_by_backrefs.items():
        version_matcher = version_matchers[dep_name]
        if not sum([
                version_matcher(provided.version_matcher.version or provided.package.version)
                for provided in provided_by_pkgs
        ]):
            if source == PackageSource.REPO:
                raise DependencyVersionMismatch(
                    version_found={
                        provided.name: provided.package.version for provided in provided_by_pkgs
                    },
                    dependency_line=version_matcher.line,
                    who_depends=aur_pkg_name,
                    depends_on=dep_name,
                    location=source,
                )
            else:
                del deps[dep_name]
                not_found_deps.append(dep_name)

    return not_found_deps


def get_aur_pkg_deps_and_version_matchers(aur_pkg: AURPackageInfo) -> Dict[str, VersionMatcher]:
    deps: Dict[str, VersionMatcher] = {}
    for dep in (aur_pkg.depends or []) + (aur_pkg.makedepends or []) + (aur_pkg.checkdepends or []):
        name, version_matcher = get_package_name_and_version_matcher_from_depend_line(dep)
        if name not in deps:
            deps[name] = version_matcher
        else:
            deps[name].add_version_matcher(version_matcher)
    return deps


def find_missing_deps_for_aur_pkg(
        aur_pkg_name: str,
        version_matchers: Dict[str, VersionMatcher],
        aur_pkgs_info: List[AURPackageInfo]
) -> List[str]:

    # local pkgs
    not_found_local_pkgs = check_deps_versions(
        aur_pkg_name=aur_pkg_name,
        deps_pkg_names=list(version_matchers.keys()),
        version_matchers=version_matchers,
        source=PackageSource.LOCAL
    )
    if not not_found_local_pkgs:
        return []

    # repo pkgs
    not_found_repo_pkgs = check_deps_versions(
        aur_pkg_name=aur_pkg_name,
        deps_pkg_names=not_found_local_pkgs,
        version_matchers=version_matchers,
        source=PackageSource.REPO
    )

    if not not_found_repo_pkgs:
        return []

    # check versions of explicitly chosen AUR packages which could be deps:
    for aur_pkg in aur_pkgs_info:
        pkg_name = aur_pkg.name
        if pkg_name not in not_found_repo_pkgs:
            continue
        version_matcher = version_matchers[pkg_name]
        if not version_matcher(aur_pkg.version):
            raise DependencyVersionMismatch(
                version_found=aur_pkg.version,
                dependency_line=version_matcher.line,
                who_depends=aur_pkg_name,
                depends_on=pkg_name,
                location=PackageSource.AUR
            )
        not_found_repo_pkgs.remove(pkg_name)

    if not not_found_repo_pkgs:
        return []

    # try finding those packages in AUR
    aur_deps_info, not_found_aur_deps = find_aur_packages(
        not_found_repo_pkgs
    )
    # @TODO: find packages Provided by AUR packages
    if not_found_aur_deps:
        problem_packages_names = []
        for aur_pkg in aur_pkgs_info:
            deps = get_aur_pkg_deps_and_version_matchers(aur_pkg).keys()
            for not_found_pkg in not_found_aur_deps:
                if not_found_pkg in deps:
                    problem_packages_names.append(aur_pkg.name)
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

    return not_found_repo_pkgs


def find_aur_deps(package_names: List[str]) -> Dict[str, List[str]]:
    new_aur_deps: List[str] = []
    result_aur_deps: Dict[str, List[str]] = {
        aur_pkg_name: []
        for aur_pkg_name in package_names
    }

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


def find_repo_deps_of_aur_pkgs(package_names: List[str]) -> List[str]:
    local_pkg_names = PackageDB.get_local_pkgnames()
    local_provided_names = PackageDB.get_local_provided_dict().keys()
    new_dep_names: List[str] = []
    for pkg_name in package_names:
        pkg = find_aur_packages([pkg_name])[0][0]
        for dep_line in pkg.depends:
            dep_name, _vm = get_package_name_and_version_matcher_from_depend_line(dep_line)
            if (
                    dep_name in new_dep_names
            ) or (
                dep_name in local_pkg_names
            ) or (
                dep_name in local_provided_names
            ):
                continue
            try:
                PackageDB.find_repo_package(dep_name)
            except PackagesNotFoundInRepo:
                continue
            new_dep_names.append(dep_name)
    return new_dep_names
