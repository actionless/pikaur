import sys
from datetime import datetime
from multiprocessing.pool import ThreadPool
from typing import Any, Dict, Tuple, List, Iterable, Union, Set

import pyalpm

from .i18n import _
from .config import PikaurConfig
from .core import DataType, PackageSource, return_exception
from .pprint import (
    color_line, bold_line, format_paragraph, pretty_format_repo_name,
    print_status_message,
)
from .pacman import PackageDB
from .aur import AURPackageInfo, aur_rpc_search_name_desc, get_all_aur_packages, get_all_aur_names
from .args import PikaurArgs
from .exceptions import AURError


@return_exception
def aur_thread_worker(search_word):
    result = aur_rpc_search_name_desc(search_word)
    return search_word, result


@return_exception
def package_search_thread_repo(index: str, args: Dict[str, Any]) -> Tuple[str, List[Any]]:
    if args['query']:
        result = PackageDB.search_repo(
            args['query'], names_only=args['namesonly']
        )
        index = ' '.join((args['index'], args['query'], ))
    else:
        result = PackageDB.get_repo_list(quiet=True)
    return index, result


@return_exception
def package_search_thread_aur(args: Dict[str, Any]) -> Dict[str, Any]:
    if args['queries']:
        with ThreadPool() as pool:
            result = {}
            for thread_result in pool.map(aur_thread_worker, args['queries']):
                if isinstance(thread_result, Exception):
                    return {str(PackageSource.AUR): thread_result}
                query, query_result = thread_result
                result[query] = query_result
        if args['namesonly']:
            for subindex, subresult in result.items():
                result[subindex] = [
                    pkg for pkg in subresult
                    if subindex in pkg.name
                ]
    else:
        if args['quiet']:
            class TmpNameType(DataType):
                name = None
            result = {'all': [
                TmpNameType(name=name) for name in get_all_aur_names()
            ]}
        else:
            result = {'all': get_all_aur_packages()}
    return result


@return_exception
def package_search_thread_router(args: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    index = args['index']
    result: Any = None
    if index == PackageSource.LOCAL:
        result = {
            pkg_name: pkg.version
            for pkg_name, pkg in PackageDB.get_local_dict(quiet=True).items()
        }
    elif str(index).startswith(str(PackageSource.REPO)):
        index, result = package_search_thread_repo(index, args)
    elif index == PackageSource.AUR:
        result = package_search_thread_aur(args)
    if not args.get('quiet'):
        sys.stderr.write('#')
    return index, result


def join_search_results(all_aur_results: List[List[AURPackageInfo]]) -> Iterable[AURPackageInfo]:
    aur_pkgs_nameset: Set[str] = set()
    for search_results in all_aur_results:
        new_aur_pkgs_nameset = set([result.name for result in search_results])
        if aur_pkgs_nameset:
            aur_pkgs_nameset = aur_pkgs_nameset.intersection(new_aur_pkgs_nameset)
        else:
            aur_pkgs_nameset = new_aur_pkgs_nameset
    return {
        result.name: result
        for result in all_aur_results[0]
        if result.name in aur_pkgs_nameset
    }.values()


def print_package_search_results(
        packages: Iterable[Union[AURPackageInfo, pyalpm.Package]],
        local_pkgs_versions: Dict[str, str],
        args: PikaurArgs
) -> None:

    def get_sort_key(pkg: AURPackageInfo) -> float:
        if getattr(pkg, "numvotes", None) is not None:
            return (pkg.numvotes + 1) * (pkg.popularity + 1)
        return 1

    local_pkgs_names = local_pkgs_versions.keys()
    for package in sorted(
            packages,
            key=get_sort_key,
            reverse=True
    ):
        # @TODO: return only packages for the current architecture
        pkg_name = package.name
        if args.quiet:
            print(pkg_name)
        else:

            repo = color_line('aur/', 9)
            if isinstance(package, pyalpm.Package):
                repo = pretty_format_repo_name(package.db.name)

            groups = ''
            if getattr(package, 'groups', None):
                groups = color_line('({}) '.format(' '.join(package.groups)), 4)

            installed = ''
            if pkg_name in local_pkgs_names:
                if package.version != local_pkgs_versions[pkg_name]:
                    installed = color_line(_("[installed: {version}]").format(
                        version=local_pkgs_versions[pkg_name],
                    ) + ' ', 14)
                else:
                    installed = color_line(_("[installed]") + ' ', 14)

            rating = ''
            if getattr(package, "numvotes", None) is not None:
                rating = color_line('({}, {:.2f})'.format(
                    package.numvotes,
                    package.popularity
                ), 3)

            color_config = PikaurConfig().colors
            version_color: int = color_config.get('Version')  # type: ignore
            version = package.version

            if getattr(package, "outofdate", None) is not None:
                version_color: int = color_config.get('VersionDiffOld')  # type: ignore
                version = "{} [{}: {}]".format(
                    package.version,
                    _("outofdate"),
                    datetime.fromtimestamp(package.outofdate).strftime('%Y/%m/%d')
                )

            print("{}{} {} {}{}{}".format(
                repo,
                bold_line(pkg_name),
                color_line(version, version_color),
                groups,
                installed,
                rating
            ))
            print(format_paragraph(f'{package.desc}'))


def cli_search_packages(args: PikaurArgs) -> None:
    search_query = args.positional or []
    REPO_ONLY = args.repo  # pylint: disable=invalid-name
    AUR_ONLY = args.aur  # pylint: disable=invalid-name
    if not args.quiet:
        progressbar_length = max(len(search_query), 1) + (not REPO_ONLY) + (not AUR_ONLY)
        sys.stderr.write(_("Searching... [{bar}]").format(bar='-' * progressbar_length))
        sys.stderr.write('\x1b[\bb' * (progressbar_length + 1))
    with ThreadPool() as pool:
        results = pool.map(package_search_thread_router, [
            {
                "index": PackageSource.LOCAL,
                "quiet": args.quiet,
            }
        ] + (
            [
                {
                    "index": str(PackageSource.REPO) + search_word,
                    "query": search_word,
                    "namesonly": args.namesonly,
                    "quiet": args.quiet,
                }
                for search_word in (search_query or [''])
            ] if not AUR_ONLY
            else []
        ) + (
            [
                {
                    "index": PackageSource.AUR,
                    "queries": search_query,
                    "namesonly": args.namesonly,
                    "quiet": args.quiet,
                }
            ] if not REPO_ONLY
            else []
        ))
    result = dict(results)
    for subresult in result.values():
        if isinstance(subresult, Exception):
            raise subresult
    if not args.quiet:
        sys.stderr.write('\n')

    local_pkgs_versions = result[PackageSource.LOCAL]
    if not AUR_ONLY:
        repo_result = join_search_results([
            r for k, r in result.items() if str(k).startswith(str(PackageSource.REPO))
        ])
        print_package_search_results(
            packages=repo_result,
            local_pkgs_versions=local_pkgs_versions,
            args=args
        )
    if not REPO_ONLY:
        for _key, query_result in result[PackageSource.AUR].items():
            if isinstance(query_result, AURError):
                print_status_message('AUR returned error: {}'.format(query_result))
                sys.exit(121)
            if isinstance(query_result, Exception):
                raise query_result
        aur_result = join_search_results([
            r for k, r in result[PackageSource.AUR].items()
        ])
        print_package_search_results(
            packages=aur_result,
            local_pkgs_versions=local_pkgs_versions,
            args=args
        )
