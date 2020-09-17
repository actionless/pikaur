""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import sys
from multiprocessing.pool import ThreadPool
from typing import Any, Dict, List, Iterable, Set, TypeVar

import pyalpm

from .i18n import _
from .pprint import print_stderr, print_error
from .print_department import print_package_search_results, AnyPackage
from .pacman import PackageDB, get_pkg_id, refresh_pkg_db
from .aur import (
    AURPackageInfo,
    aur_rpc_search_name_desc, get_all_aur_packages, get_all_aur_names,
)
from .args import parse_args
from .exceptions import AURError, SysExit


SamePackageType = TypeVar('SamePackageType', AURPackageInfo, pyalpm.Package)


def package_search_thread_repo(query: str) -> List[pyalpm.Package]:
    args = parse_args()
    if query:
        result = PackageDB.search_repo(
            query, names_only=args.namesonly
        )
    else:
        result = PackageDB.get_repo_list(quiet=True)
    if not args.quiet:
        sys.stderr.write('#')
    return result


def filter_aur_results(
        results: Dict[str, List[AURPackageInfo]],
        query: str
) -> Dict[str, List[AURPackageInfo]]:
    filtered_results: Dict[str, List[AURPackageInfo]] = {}
    for _q, pkgs in results.items():
        for pkg in pkgs:
            if query in pkg.name or query in (pkg.desc or ''):
                filtered_results.setdefault(_q, []).append(pkg)
    return filtered_results


def package_search_thread_aur(queries: List[str]) -> Dict[str, List[Any]]:  # pylint: disable=too-many-branches
    args = parse_args()
    result = {}
    if queries:
        use_as_filters: List[str] = []
        with ThreadPool() as pool:
            requests = {}
            for query in queries:
                requests[query] = pool.apply_async(aur_rpc_search_name_desc, (query, ))
            pool.close()
            for query, request in requests.items():
                try:
                    result[query] = request.get()
                except AURError as exc:
                    if exc.error == "Too many package results.":
                        print_error(
                            _("AUR: Too many package results for '{query}'").format(
                                query=query
                            )
                        )
                        use_as_filters.append(query)
                    elif exc.error == "Query arg too small.":
                        print_error(
                            _("AUR: Query arg too small '{query}'").format(
                                query=query
                            )
                        )
                        use_as_filters.append(query)
                    else:
                        raise
            pool.join()
        for query in use_as_filters:
            result = filter_aur_results(result, query)
        if args.namesonly:
            for subindex, subresult in result.items():
                result[subindex] = [
                    pkg for pkg in subresult
                    if subindex in pkg.name
                ]
    else:
        if args.quiet:
            result = {'all': [
                AURPackageInfo(
                    name=name,
                    packagebase=name,
                    version="0",
                ) for name in get_all_aur_names()
            ]}
        else:
            result = {'all': get_all_aur_packages()}
    if not args.quiet:
        sys.stderr.write('#')
    return result


def package_search_thread_local() -> Dict[str, str]:
    result = {
        pkg_name: pkg.version
        for pkg_name, pkg in PackageDB.get_local_dict(quiet=True).items()
    }
    if not parse_args().quiet:
        sys.stderr.write('#')
    return result


def join_search_results(
        all_search_results: List[List[SamePackageType]]
) -> Iterable[SamePackageType]:
    pkgnames_set: Set[str] = set()
    for search_results in all_search_results:
        new_pkgnames_set = set(get_pkg_id(result) for result in search_results)
        if pkgnames_set:
            pkgnames_set = pkgnames_set.intersection(new_pkgnames_set)
        else:
            pkgnames_set = new_pkgnames_set
    return {
        get_pkg_id(result): result
        for result in all_search_results[0]
        if get_pkg_id(result) in pkgnames_set
    }.values()


def cli_search_packages(enumerated=False) -> List[AnyPackage]:  # pylint: disable=too-many-locals
    refresh_pkg_db()

    args = parse_args()
    search_query = args.positional or []
    REPO_ONLY = args.repo  # pylint: disable=invalid-name
    AUR_ONLY = args.aur  # pylint: disable=invalid-name

    if not args.quiet:
        progressbar_length = max(len(search_query), 1) + (not REPO_ONLY) + (not AUR_ONLY)
        print_stderr(_("Searching... [{bar}]").format(bar='-' * progressbar_length), end='')
        print_stderr('\x1b[\bb' * (progressbar_length + 1), end='')

    with ThreadPool() as pool:
        request_local = pool.apply_async(package_search_thread_local, ())
        requests_repo = [
            pool.apply_async(package_search_thread_repo, (search_word, ))
            for search_word in (search_query or [''])
        ] if not AUR_ONLY else []
        request_aur = pool.apply_async(
            package_search_thread_aur, (search_query,)
        ) if not REPO_ONLY else None
        pool.close()

        result_local = request_local.get()
        result_repo: List[List[pyalpm.Package]] = []
        for request_repo in requests_repo:
            pkgs_found = request_repo.get()
            if pkgs_found:
                result_repo.append(pkgs_found)
        try:
            result_aur = request_aur.get() if request_aur else None
        except AURError as exc:
            print_stderr('AUR returned error: {}'.format(exc))
            raise SysExit(121) from exc
        pool.join()

    if not args.quiet:
        sys.stderr.write('\n')

    repo_result = (
        join_search_results(result_repo)
    ) if result_repo and not AUR_ONLY else []
    aur_result = (
        join_search_results(list(result_aur.values()))
    ) if result_aur and not REPO_ONLY else []

    return print_package_search_results(
        repo_packages=repo_result,
        aur_packages=aur_result,
        local_pkgs_versions=result_local,
        enumerated=enumerated,
    )
