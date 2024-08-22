"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

from multiprocessing.pool import ThreadPool
from typing import TYPE_CHECKING

from .aur import find_aur_packages, find_aur_provided_deps
from .exceptions import (
    DependencyVersionMismatchError,
    PackagesNotFoundInAURError,
    PackagesNotFoundInRepoError,
)
from .i18n import translate
from .logging_extras import create_logger
from .pacman import PackageDB
from .pikaprint import print_error
from .pikatypes import PackageSource
from .version import VersionMatcher

if TYPE_CHECKING:
    from .pikatypes import AURPackageInfo


logger = create_logger("aur_deps")


def check_deps_versions(
        deps_pkg_names: list[str],
        version_matchers: dict[str, VersionMatcher],
        source: PackageSource,
) -> list[str]:
    deps_lines = [
        version_matchers[dep_name].line
        for dep_name in deps_pkg_names
    ]
    if source == PackageSource.REPO:
        return PackageDB.get_not_found_repo_packages(deps_lines)
    return PackageDB.get_not_found_local_packages(deps_lines)


def get_aur_pkg_deps_and_version_matchers(
        aur_pkg: "AURPackageInfo",
        *,
        skip_check_depends: bool = False,
        skip_runtime_deps: bool = False,
) -> dict[str, VersionMatcher]:
    deps: dict[str, VersionMatcher] = {}
    for dep_line in (
            (aur_pkg.depends or [])
            + (aur_pkg.makedepends or [])
            + (aur_pkg.runtimedepends if (not skip_runtime_deps and aur_pkg.runtimedepends) else [])
            + (aur_pkg.checkdepends if (not skip_check_depends and aur_pkg.checkdepends) else [])
    ):
        version_matcher = VersionMatcher(dep_line, is_pkg_deps=True)
        name = version_matcher.pkg_name
        if name not in deps:
            deps[name] = version_matcher
        else:
            deps[name].add_version_matcher(version_matcher)
    return deps


def find_dep_graph_to(
        from_pkg: "AURPackageInfo",
        to_pkgs: "list[AURPackageInfo]",
        all_pkgs: "list[AURPackageInfo]",
        *,
        skip_check_depends: bool = False,
) -> "list[AURPackageInfo]":
    result: list[AURPackageInfo] = []
    if len(to_pkgs) == 1:
        possible_end_pkg = to_pkgs[0]
        possible_end_pkgs_deps = (
            possible_end_pkg.depends
            + ([] if skip_check_depends else possible_end_pkg.checkdepends)
            + possible_end_pkg.makedepends
        )
        for name in [from_pkg.name, *from_pkg.provides]:
            if name in possible_end_pkgs_deps:
                result.append(possible_end_pkg)
                break
        for pkg in all_pkgs:
            for name in [pkg.name, *pkg.provides]:
                if (
                        name in possible_end_pkgs_deps
                ) and (
                        from_pkg != pkg
                ):
                    result += find_dep_graph_to(
                        from_pkg=from_pkg,
                        to_pkgs=[pkg],
                        all_pkgs=all_pkgs,
                    )
                    break
        return result
    for possible_end_pkg in to_pkgs:
        result += find_dep_graph_to(
            from_pkg=from_pkg,
            to_pkgs=[possible_end_pkg],
            all_pkgs=all_pkgs,
        )
    return result


def handle_not_found_aur_pkgs(
        aur_pkg_name: str,
        aur_pkgs_info: "list[AURPackageInfo]",
        not_found_aur_deps: list[str],
        requested_aur_pkgs_info: "list[AURPackageInfo]",
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
                except PackagesNotFoundInRepoError:
                    pass
                else:
                    version_found = failed_pkg.version
                    if not_found_pkg in all_repo_provided_packages:
                        version_found = str({
                            provided.name: provided.package.version
                            for provided in all_repo_provided_packages[not_found_pkg]
                        })
                    raise DependencyVersionMismatchError(
                        version_found=version_found,
                        dependency_line=version_matcher.line,
                        who_depends=aur_pkg_name,
                        depends_on=not_found_pkg,
                        location=PackageSource.REPO,
                    )

                not_found_local_pkgs = PackageDB.get_not_found_local_packages([not_found_pkg])
                if not not_found_local_pkgs:
                    raise DependencyVersionMismatchError(
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
                problem_packages_names.extend(
                    dependant_pkg.name
                    for dependant_pkg in find_dep_graph_to(
                        from_pkg=aur_pkg,
                        to_pkgs=requested_aur_pkgs_info,
                        all_pkgs=aur_pkgs_info,
                    )
                )
                break

    raise PackagesNotFoundInAURError(
        packages=not_found_aur_deps,
        wanted_by=problem_packages_names,
    )


def check_requested_pkgs(
        aur_pkg_name: str,
        version_matchers: dict[str, VersionMatcher],
        aur_pkgs_info: "list[AURPackageInfo]",
) -> list[str]:
    # check versions of explicitly chosen AUR packages which could be deps:
    # @TODO: also check against user-requested repo packages
    not_found_in_requested_pkgs: list[str] = list(version_matchers.keys())
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
            if (
                    not version_matcher(aur_pkg.version)
                    and (
                        not aur_pkg.provides or not min(
                            version_matcher(VersionMatcher(prov_line).version)
                            for prov_line in aur_pkg.provides
                        )
                    )
            ):
                raise DependencyVersionMismatchError(
                    version_found=aur_pkg.version,
                    dependency_line=version_matcher.line,
                    who_depends=aur_pkg_name,
                    depends_on=dep_name,
                    location=PackageSource.AUR,
                )
            not_found_in_requested_pkgs.remove(dep_name)
    return not_found_in_requested_pkgs


def find_missing_deps_for_aur_pkg(
        aur_pkg_name: str,
        version_matchers: dict[str, VersionMatcher],
        aur_pkgs_info: "list[AURPackageInfo]",
        requested_aur_pkgs_info: "list[AURPackageInfo]",
) -> list[str]:

    # check if any of packages requested to install by user
    # are satisfying any of the deps:
    not_found_in_requested_pkgs = check_requested_pkgs(
        aur_pkg_name=aur_pkg_name,
        version_matchers=version_matchers,
        aur_pkgs_info=aur_pkgs_info,
    )
    if not not_found_in_requested_pkgs:
        logger.debug("find_missing_deps_for_aur_pkg: NOT not_found_in_requested_pkgs")
        return []

    # check among local pkgs:
    not_found_local_pkgs = check_deps_versions(
        deps_pkg_names=not_found_in_requested_pkgs,
        version_matchers=version_matchers,
        source=PackageSource.LOCAL,
    )
    if not not_found_local_pkgs:
        logger.debug("find_missing_deps_for_aur_pkg: NOT not_found_local_pkgs")
        return []

    # repo pkgs:
    not_found_repo_pkgs = check_deps_versions(
        deps_pkg_names=not_found_local_pkgs,
        version_matchers=version_matchers,
        source=PackageSource.REPO,
    )
    if not not_found_repo_pkgs:
        logger.debug("find_missing_deps_for_aur_pkg: NOT not_found_repo_pkgs")
        return []

    # try finding those packages in AUR
    aur_deps_info, not_found_aur_deps = find_aur_packages(
        not_found_repo_pkgs,
    )
    provided_aur_deps_info, not_found_aur_deps = find_aur_provided_deps(
        not_found_aur_deps,
        version_matchers=version_matchers,
    )
    aur_deps_info += provided_aur_deps_info

    handle_not_found_aur_pkgs(
        aur_pkg_name=aur_pkg_name,
        aur_pkgs_info=aur_pkgs_info,
        not_found_aur_deps=not_found_aur_deps,
        requested_aur_pkgs_info=requested_aur_pkgs_info,
    )

    # check versions of found AUR packages:
    logger.debug("find_missing_deps_for_aur_pkg: version_matchers={}", version_matchers)
    for aur_dep_info in aur_deps_info:
        aur_dep_name = aur_dep_info.name
        version_matcher = version_matchers.get(
            aur_dep_name,
        )
        pkg_version_matchers: list[VersionMatcher] = []
        if version_matcher:
            pkg_version_matchers = [version_matcher]
        else:
            for provide in aur_dep_info.provides:
                version_matcher = version_matchers.get(VersionMatcher(provide).pkg_name)
                if version_matcher is not None:
                    pkg_version_matchers.append(version_matcher)
        logger.debug(
            "find_missing_deps_for_aur_pkg: {} pkg version_matchers={}",
            aur_dep_name, pkg_version_matchers,
        )
        for version_matcher in pkg_version_matchers:
            if not version_matcher(aur_dep_info.version):
                raise DependencyVersionMismatchError(
                    version_found=aur_dep_info.version,
                    dependency_line=version_matcher.line,
                    who_depends=aur_pkg_name,
                    depends_on=aur_dep_name,
                    location=PackageSource.AUR,
                )
            # not_found_repo_pkgs.remove(version_matcher.pkg_name)

    return not_found_repo_pkgs


def find_aur_deps(  # pylint: disable=too-many-branches
        aur_pkgs_infos: "list[AURPackageInfo]",
        skip_checkdeps_for_pkgnames: list[str] | None = None,
        *,
        skip_runtime_deps: bool = False,
) -> dict[str, list[str]]:
    new_aur_deps: list[str] = []
    package_names = [
        aur_pkg.name
        for aur_pkg in aur_pkgs_infos
    ]
    logger.debug("find_aur_deps: package_names={}", package_names)
    result_aur_deps: dict[str, list[str]] = {}

    initial_pkg_infos = initial_pkg_infos2_todo = aur_pkgs_infos[:]  # @TODO: var name
    iter_package_names: list[str] = []
    while iter_package_names or initial_pkg_infos:
        all_deps_for_aur_packages = {}
        if initial_pkg_infos:
            aur_pkgs_info = initial_pkg_infos
            not_found_aur_pkgs: list[str] = []
            initial_pkg_infos = []
        else:
            aur_pkgs_info, not_found_aur_pkgs = find_aur_packages(iter_package_names)
            provided_aur_deps_info, not_found_aur_pkgs = find_aur_provided_deps(
                not_found_aur_pkgs,
            )
            aur_pkgs_info += provided_aur_deps_info
        if not_found_aur_pkgs:
            logger.debug("not_found_aur_pkgs={}", not_found_aur_pkgs)
            raise PackagesNotFoundInAURError(packages=not_found_aur_pkgs)
        for aur_pkg in aur_pkgs_info:
            aur_pkg_deps = get_aur_pkg_deps_and_version_matchers(
                aur_pkg,
                skip_check_depends=aur_pkg.name in (skip_checkdeps_for_pkgnames or []),
                skip_runtime_deps=skip_runtime_deps,
            )
            if aur_pkg_deps:
                all_deps_for_aur_packages[aur_pkg.name] = aur_pkg_deps

        not_found_local_pkgs: list[str] = []
        with ThreadPool() as pool:
            all_requests = {}
            for aur_pkg_name, deps_for_aur_package in all_deps_for_aur_packages.items():
                all_requests[aur_pkg_name] = pool.apply_async(
                    find_missing_deps_for_aur_pkg, (
                        aur_pkg_name,
                        deps_for_aur_package,
                        aur_pkgs_info,
                        initial_pkg_infos2_todo,
                    ),
                )
            pool.close()
            pool.join()
            for aur_pkg_name, request in all_requests.items():
                try:
                    results = request.get()
                except Exception as exc:
                    logger.debug(
                        "exception during aur search: {}: {}",
                        exc.__class__.__name__, exc,
                    )
                    print_error(translate(
                        "Can't resolve dependencies for AUR package '{pkg}':",
                    ).format(pkg=aur_pkg_name))
                    raise
                not_found_local_pkgs += results
                for dep_pkg_name in results:
                    if dep_pkg_name not in package_names:
                        result_aur_deps.setdefault(aur_pkg_name, []).append(dep_pkg_name)

        iter_package_names = []
        for pkg_name in not_found_local_pkgs:
            if pkg_name not in new_aur_deps and pkg_name not in package_names:
                new_aur_deps.append(pkg_name)
                iter_package_names.append(pkg_name)

    logger.debug("find_aur_deps: result_aur_deps={}", result_aur_deps)
    return result_aur_deps


def get_aur_deps_list(aur_pkgs_infos: "list[AURPackageInfo]") -> "list[AURPackageInfo]":
    aur_deps_relations = find_aur_deps(aur_pkgs_infos)
    all_aur_deps = list({
        dep
        for _pkg, deps in aur_deps_relations.items()
        for dep in deps
    })
    return find_aur_packages(all_aur_deps)[0]


def _find_repo_deps_of_aur_pkg(
        aur_pkg: "AURPackageInfo",
        all_aur_pkgs: "list[AURPackageInfo]",
        *,
        skip_check_depends: bool = False,
) -> list[VersionMatcher]:
    new_deps_vms: list[VersionMatcher] = []

    version_matchers = get_aur_pkg_deps_and_version_matchers(
        aur_pkg, skip_check_depends=skip_check_depends,
    )

    not_found_in_requested_pkgs = check_requested_pkgs(
        aur_pkg_name=aur_pkg.name,
        version_matchers={
            name: version_matchers[name]
            for name in PackageDB.get_not_found_local_packages(
                [vm.line for vm in version_matchers.values()],
            )
        },
        aur_pkgs_info=all_aur_pkgs,
    )

    for dep_name, version_matcher in version_matchers.items():
        if dep_name not in not_found_in_requested_pkgs:
            continue
        try:
            PackageDB.find_repo_package(version_matcher.line)
        except PackagesNotFoundInRepoError:
            continue
        else:
            new_deps_vms.append(version_matcher)
    return new_deps_vms


def find_repo_deps_of_aur_pkgs(
        aur_pkgs: "list[AURPackageInfo]",
        skip_checkdeps_for_pkgnames: list[str],
) -> list[VersionMatcher]:
    new_dep_names: list[VersionMatcher] = []
    with ThreadPool() as pool:
        results = [
            pool.apply_async(
                _find_repo_deps_of_aur_pkg,
                (
                    aur_pkg,
                    aur_pkgs,
                ),
                {
                    "skip_check_depends": aur_pkg.name in (skip_checkdeps_for_pkgnames or []),
                },
            )
            for aur_pkg in aur_pkgs
        ]
        pool.close()
        pool.join()
        for result in results:
            new_dep_names += result.get()
    return list(set(new_dep_names))
