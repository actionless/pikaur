"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import sys
from collections.abc import Iterable
from multiprocessing.pool import ThreadPool
from typing import TYPE_CHECKING

from .args import parse_args
from .aur import (
    AurRPCErrors,
    aur_rpc_search,
    get_all_aur_names,
    get_all_aur_packages,
)
from .exceptions import AURError, SysExit
from .i18n import translate
from .logging_extras import create_logger
from .pacman import PackageDB, get_pkg_id, refresh_pkg_db_if_needed
from .pikaprint import print_error, print_stderr
from .pikatypes import AnyPackage, AURPackageInfo, SamePackageT
from .print_department import print_package_search_results

if TYPE_CHECKING:
    import pyalpm

logger = create_logger("search")


def filter_search_results(
        results: dict[str, list[SamePackageT]],
        query: str,
        *,
        names_only: bool = False,
) -> dict[str, list[SamePackageT]]:
    filtered_results: dict[str, list[SamePackageT]] = {}
    for _q, pkgs in results.items():
        for pkg in pkgs:
            if (
                    query in pkg.name
            ) or (
                not names_only
                and pkg.desc
                and (query in pkg.desc)
            ):
                filtered_results.setdefault(_q, []).append(pkg)
    return filtered_results


def join_search_results(
        all_search_results: list[list[SamePackageT]],
) -> Iterable[SamePackageT]:
    if not all_search_results:
        return []
    pkgnames_set: set[str] = set()
    for search_results in all_search_results:
        new_pkgnames_set = {get_pkg_id(result) for result in search_results}
        pkgnames_set = (
            pkgnames_set.intersection(new_pkgnames_set)
            if pkgnames_set else
            new_pkgnames_set
        )
    return {
        get_pkg_id(result): result
        for result in all_search_results[0]
        if get_pkg_id(result) in pkgnames_set
    }.values()


def package_search_thread_aur(  # pylint: disable=too-many-branches
        queries: list[str],
) -> list[AURPackageInfo]:
    args = parse_args()
    logger.debug("queries: {}", queries)
    result = {}
    if queries:
        use_as_filters: list[str] = []
        with ThreadPool() as pool:
            requests = {}
            for query in queries:
                requests[query] = pool.apply_async(aur_rpc_search, (query, ))
            pool.close()
            for query, request in requests.items():
                try:
                    result[query] = request.get()
                except AURError as exc:
                    if exc.error == AurRPCErrors.TOO_MANY_RESULTS:
                        print_error(
                            translate("AUR: Too many package results for '{query}'").format(
                                query=query,
                            ),
                        )
                        use_as_filters.append(query)
                    elif exc.error == AurRPCErrors.QUERY_TOO_SMALL:
                        print_error(
                            translate("AUR: Query arg too small '{query}'").format(
                                query=query,
                            ),
                        )
                        use_as_filters.append(query)
                    else:
                        raise
            pool.join()
        for query in use_as_filters:
            result = filter_search_results(result, query, names_only=args.namesonly)
        if args.namesonly:
            for subindex, subresult in result.items():
                result[subindex] = [
                    pkg for pkg in subresult
                    if subindex in pkg.name
                ]
    elif args.quiet or args.list:
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


def package_search_thread_repo_worker(
        query: str, db_names: list[str] | None = None,
) -> "list[pyalpm.Package]":
    args = parse_args()
    result = (
        PackageDB.search_repo(query, names_only=args.namesonly, db_names=db_names)
        if (query or db_names) else
        PackageDB.get_repo_list(quiet=True)
    )
    if not args.quiet:
        sys.stderr.write("#")
    return result


def package_search_thread_repo(
        search_query: list[str], db_names: list[str] | None = None,
) -> "list[pyalpm.Package]":
    args = parse_args()
    use_as_filters: list[str] = []
    result_repo = {}
    with ThreadPool() as pool:
        requests_repo = {
            search_word: pool.apply_async(
                package_search_thread_repo_worker, (search_word, db_names),
            )
            for search_word in (search_query or [""])
        }
        for search_word, request_repo in requests_repo.items():
            pkgs_found = request_repo.get()
            if pkgs_found:
                result_repo[search_word] = pkgs_found
            else:
                use_as_filters.append(search_word)
        for query in use_as_filters:
            result_repo = filter_search_results(result_repo, query, names_only=args.namesonly)
    joined_repo_results = join_search_results(list(result_repo.values()))
    return list(joined_repo_results)


def package_search_thread_local() -> dict[str, str]:
    result = {
        pkg_name: pkg.version
        for pkg_name, pkg in PackageDB.get_local_dict(quiet=True).items()
    }
    if not parse_args().quiet:
        sys.stderr.write("#")
    return result


def search_packages(
        *, enumerated: bool = False,
) -> "list[AnyPackage]":
    refresh_pkg_db_if_needed()

    args = parse_args()
    search_query = ((not args.list) and args.positional) or []
    repo_query = args.positional if args.list else None
    repo_only = (
        args.repo
        or (
            args.list
            and args.positional
            and ("aur" not in args.positional)
        )
    )
    aur_only = (
        args.aur
        or (
            args.list
            and (len(args.positional) == 1)
            and (args.positional[0] == "aur")
        )
    )

    if not args.quiet:
        progressbar_length = max(len(search_query), 1) + (not repo_only) + (not aur_only)
        print_stderr(translate("Searching... [{bar}]").format(bar="-" * progressbar_length), end="")
        print_stderr("\x1b[1D" * (progressbar_length + 1), end="")

    with ThreadPool() as pool:
        request_local = pool.apply_async(package_search_thread_local, ())
        request_repo = pool.apply_async(
            package_search_thread_repo, (search_query, repo_query),
        ) if not aur_only else None
        request_aur = pool.apply_async(
            package_search_thread_aur, (search_query,),
        ) if not repo_only else None
        pool.close()

        result_local = request_local.get()
        result_repo = request_repo.get() if request_repo else []
        result_aur = []
        if request_aur:
            try:
                result_aur = request_aur.get()
            except AURError as exc:
                message = translate("AUR returned error:")
                print_stderr(f"{message} {exc}")
                raise SysExit(121) from exc
        pool.join()

    if not args.quiet:
        sys.stderr.write("\n")

    return print_package_search_results(
        repo_packages=result_repo,
        aur_packages=result_aur,
        local_pkgs_versions=result_local,
        enumerated=enumerated,
        list_mode=bool(args.list),
    )


def cli_search_packages() -> None:
    search_packages()
