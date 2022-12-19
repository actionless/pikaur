"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import sys
from multiprocessing.pool import ThreadPool
from typing import Iterable, TypeVar

import pyalpm

from .args import parse_args
from .aur import AURPackageInfo, aur_rpc_search_name_desc, get_all_aur_names, get_all_aur_packages
from .exceptions import AURError, SysExit
from .i18n import translate
from .pacman import PackageDB, get_pkg_id, refresh_pkg_db_if_needed
from .pprint import print_error, print_stderr
from .print_department import AnyPackage, print_package_search_results

SamePackageTypeT = TypeVar("SamePackageTypeT", AURPackageInfo, pyalpm.Package)


def package_search_thread_repo(query: str) -> list[pyalpm.Package]:
    args = parse_args()
    if query:
        result = PackageDB.search_repo(
            query, names_only=args.namesonly
        )
    else:
        result = PackageDB.get_repo_list(quiet=True)
    if not args.quiet:
        sys.stderr.write("#")
    return result


def filter_aur_results(
        results: dict[str, list[AURPackageInfo]],
        query: str,
        *,
        names_only: bool = False,
) -> dict[str, list[AURPackageInfo]]:
    filtered_results: dict[str, list[AURPackageInfo]] = {}
    for _q, pkgs in results.items():
        for pkg in pkgs:
            if (
                    query in pkg.name
            ) or (
                not names_only and
                (query in (pkg.desc or ""))
            ):
                filtered_results.setdefault(_q, []).append(pkg)
    return filtered_results


def package_search_thread_aur(  # pylint: disable=too-many-branches
        queries: list[str]
) -> list[AURPackageInfo]:
    args = parse_args()
    result = {}
    if queries:
        use_as_filters: list[str] = []
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
                            translate("AUR: Too many package results for '{query}'").format(
                                query=query
                            )
                        )
                        use_as_filters.append(query)
                    elif exc.error == "Query arg too small.":
                        print_error(
                            translate("AUR: Query arg too small '{query}'").format(
                                query=query
                            )
                        )
                        use_as_filters.append(query)
                    else:
                        raise
            pool.join()
        for query in use_as_filters:
            result = filter_aur_results(result, query, names_only=args.namesonly)
        if args.namesonly:
            for subindex, subresult in result.items():
                result[subindex] = [
                    pkg for pkg in subresult
                    if subindex in pkg.name
                ]
    else:
        if args.quiet:
            result = {"all": [
                AURPackageInfo(
                    name=name,
                    packagebase=name,
                    version="0",
                ) for name in get_all_aur_names()
            ]}
        else:
            result = {"all": get_all_aur_packages()}
    if not args.quiet:
        sys.stderr.write("#")
    return list(join_search_results(list(result.values())))


def package_search_thread_local() -> dict[str, str]:
    result = {
        pkg_name: pkg.version
        for pkg_name, pkg in PackageDB.get_local_dict(quiet=True).items()
    }
    if not parse_args().quiet:
        sys.stderr.write("#")
    return result


def join_search_results(
        all_search_results: list[list[SamePackageTypeT]]
) -> Iterable[SamePackageTypeT]:
    if not all_search_results:
        return []
    pkgnames_set: set[str] = set()
    for search_results in all_search_results:
        new_pkgnames_set = {get_pkg_id(result) for result in search_results}
        if pkgnames_set:
            pkgnames_set = pkgnames_set.intersection(new_pkgnames_set)
        else:
            pkgnames_set = new_pkgnames_set
    return {
        get_pkg_id(result): result
        for result in all_search_results[0]
        if get_pkg_id(result) in pkgnames_set
    }.values()


def search_packages(  # pylint: disable=too-many-locals
        *, enumerated: bool = False
) -> list[AnyPackage]:
    refresh_pkg_db_if_needed()

    args = parse_args()
    search_query = args.positional or []
    repo_only = args.repo
    aur_only = args.aur

    if not args.quiet:
        progressbar_length = max(len(search_query), 1) + (not repo_only) + (not aur_only)
        print_stderr(translate("Searching... [{bar}]").format(bar="-" * progressbar_length), end="")
        print_stderr("\x1b[1D" * (progressbar_length + 1), end="")

    with ThreadPool() as pool:
        request_local = pool.apply_async(package_search_thread_local, ())
        requests_repo = [
            pool.apply_async(package_search_thread_repo, (search_word, ))
            for search_word in (search_query or [""])
        ] if not aur_only else []
        request_aur = pool.apply_async(
            package_search_thread_aur, (search_query,)
        ) if not repo_only else None
        pool.close()

        result_local = request_local.get()
        result_repo: list[list[pyalpm.Package]] = []
        for request_repo in requests_repo:
            pkgs_found = request_repo.get()
            if pkgs_found:
                result_repo.append(pkgs_found)
        result_aur = None
        if request_aur:
            try:
                result_aur = request_aur.get()
            except AURError as exc:
                print_stderr(f"{translate('AUR returned error:')} {exc}")
                raise SysExit(121) from exc
        pool.join()

    if not args.quiet:
        sys.stderr.write("\n")

    joined_repo_results: Iterable[pyalpm.Package] = []
    if result_repo:
        joined_repo_results = join_search_results(result_repo)
    joined_aur_results: Iterable[AURPackageInfo] = result_aur or []

    return print_package_search_results(
        repo_packages=joined_repo_results,
        aur_packages=joined_aur_results,
        local_pkgs_versions=result_local,
        enumerated=enumerated,
    )


def cli_search_packages() -> None:
    search_packages()
