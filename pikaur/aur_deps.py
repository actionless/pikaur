from .pacman import (
    PackageDB, find_local_packages, find_repo_packages,
)
from .version import (
    get_package_name_and_version_matcher_from_depend_line,
)
from .aur import find_aur_packages
from .exceptions import PackagesNotFoundInAUR, DependencyVersionMismatch


LOCAL_PKG = 'local'
REPO_PKG = 'repo'


def find_provided_pkgs(pkg_names, source):
    provided_by_backrefs = {}
    if not pkg_names:
        return provided_by_backrefs
    if source == REPO_PKG:
        provided_dict = PackageDB.get_repo_provided_dict()
    else:
        provided_dict = PackageDB.get_local_provided_dict()
    for pkg_name, provided in provided_dict.items():
        for provided_pkg in provided:
            for dep_name in pkg_names:
                if dep_name == provided_pkg.name:
                    provided_by_backrefs.setdefault(
                        dep_name, []
                    ).append((pkg_name, provided_pkg.version_matcher.version))
    return provided_by_backrefs


def check_deps_versions(aur_pkg_name, deps_pkg_names, version_matchers, source):
    # try to find explicit pkgs:
    deps_names = not_found_deps = None
    if source == REPO_PKG:
        deps_names, not_found_deps = find_repo_packages(deps_pkg_names)
    else:
        deps_names, not_found_deps = find_local_packages(deps_pkg_names)

    # try to find pkgs provided by other pkgs:
    provided_by_backrefs = find_provided_pkgs(
        pkg_names=not_found_deps,
        source=source
    )
    for dep_name in provided_by_backrefs:
        not_found_deps.remove(dep_name)
        deps_names.append(dep_name)
    if not deps_names:
        return not_found_deps

    all_pkgs_info = None
    if source == REPO_PKG:
        all_pkgs_info = PackageDB.get_repo_dict()
    else:
        all_pkgs_info = PackageDB.get_local_dict()
    # check versions of found packages:
    for dep_name in set(deps_names):
        version_matcher = version_matchers[dep_name]

        # exlicit deps:
        pkg_info = all_pkgs_info.get(dep_name)
        if pkg_info:
            if not version_matcher(pkg_info.version):
                raise DependencyVersionMismatch(
                    version_found=pkg_info.version,
                    dependency_line=version_matcher.line,
                    who_depends=aur_pkg_name,
                    depends_on=dep_name,
                    location=source,
                )

        # dep via provided pkg:
        provided_by_pkgs = provided_by_backrefs.get(dep_name)
        if provided_by_pkgs:
            fallback_version = None
            if pkg_info:
                fallback_version = pkg_info.version
            if not sum([
                    version_matcher(dep_version or fallback_version)
                    for dep_name, dep_version in provided_by_pkgs
            ]):
                raise DependencyVersionMismatch(
                    version_found=provided_by_pkgs,
                    dependency_line=version_matcher.line,
                    who_depends=aur_pkg_name,
                    depends_on=dep_name,
                    location=source,
                )
    #
    return not_found_deps


def get_aur_pkg_deps_and_version_matchers(result):
    deps = {}
    for dep in (result.depends or []) + (result.makedepends or []):
        name, version_matcher = get_package_name_and_version_matcher_from_depend_line(dep)
        deps[name] = version_matcher
    return deps


def find_deps_for_aur_pkg(aur_pkg_name, version_matchers, aur_pkgs_info):
    # repo pkgs
    not_found_deps = check_deps_versions(
        aur_pkg_name=aur_pkg_name,
        deps_pkg_names=version_matchers.keys(),
        version_matchers=version_matchers,
        source=REPO_PKG
    )

    if not not_found_deps:
        return []

    # local pkgs
    not_found_local_pkgs = check_deps_versions(
        aur_pkg_name=aur_pkg_name,
        deps_pkg_names=not_found_deps,
        version_matchers=version_matchers,
        source=LOCAL_PKG
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
                location='aur'
            )
    return not_found_local_pkgs


def find_aur_deps(package_names):

    new_aur_deps = []
    while package_names:

        all_deps_for_aur_packages = {}
        aur_pkgs_info, not_found_aur_pkgs = find_aur_packages(package_names)
        if not_found_aur_pkgs:
            raise PackagesNotFoundInAUR(packages=not_found_aur_pkgs)
        for result in aur_pkgs_info:
            aur_pkg_deps = get_aur_pkg_deps_and_version_matchers(result)
            if aur_pkg_deps:
                all_deps_for_aur_packages[result.name] = aur_pkg_deps

        not_found_local_pkgs = []
        for aur_pkg_name, deps_for_aur_package in all_deps_for_aur_packages.items():
            not_found_local_pkgs += find_deps_for_aur_pkg(
                aur_pkg_name=aur_pkg_name,
                aur_pkgs_info=aur_pkgs_info,
                version_matchers=deps_for_aur_package,
            )
        new_aur_deps += not_found_local_pkgs
        package_names = not_found_local_pkgs

    return list(set(new_aur_deps))
