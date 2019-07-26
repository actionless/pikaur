""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import sys
from multiprocessing.pool import ThreadPool
from typing import Any, Dict, List, Iterable, Union, Set, Sequence

import pyalpm

from .i18n import _
from .pprint import print_stderr
from .print_department import print_package_search_results
from .pacman import PackageDB, get_pkg_id, refresh_pkg_db
from .aur import (
    AURPackageInfo,
    aur_rpc_search_name_desc, get_all_aur_packages, get_all_aur_names,
)
from .args import parse_args
from .exceptions import AURError, SysExit


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


def package_search_thread_aur(queries: List[str]) -> Dict[str, List[Any]]:
    args = parse_args()
    result = {}
    if queries:
        with ThreadPool() as pool:
            requests = {}
            for query in queries:
                requests[query] = pool.apply_async(aur_rpc_search_name_desc, (query, ))
            pool.close()
            for query, request in requests.items():
                result[query] = request.get()
            pool.join()
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
        all_search_results: Sequence[Union[List[AURPackageInfo], List[pyalpm.Package]]]
) -> Iterable[Union[AURPackageInfo, pyalpm.Package]]:
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


def cli_search_packages() -> None:  # pylint: disable=too-many-locals
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
            raise SysExit(121)
        pool.join()

    if not args.quiet:
        sys.stderr.write('\n')

    if result_repo and not AUR_ONLY:
        repo_result = join_search_results(result_repo)
        print_package_search_results(
            packages=repo_result,
            local_pkgs_versions=result_local
        )

    if result_aur and not REPO_ONLY:
        aur_result = join_search_results(list(result_aur.values()))
        print_package_search_results(
            packages=aur_result,
            local_pkgs_versions=result_local
        )
