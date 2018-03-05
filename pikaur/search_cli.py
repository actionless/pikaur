import sys
from multiprocessing.pool import ThreadPool

from .core import DataType, MultipleTasksExecutor, LOCAL, REPO, AUR
from .pprint import color_line, bold_line, format_paragraph, pretty_format_repo_name
from .pacman import PackageDB
from .aur import (
    AurTaskWorkerSearch,
    get_all_aur_packages, get_all_aur_names,
)


def package_search_worker(args):
    index = args['index']
    result = None

    if index == LOCAL:
        result = {
            pkg_name: pkg.version
            for pkg_name, pkg in PackageDB.get_local_dict(quiet=True).items()
        }

    elif index == REPO:
        if args['query']:
            result = PackageDB.search_repo(
                args['query'], names_only=args['namesonly']
            )
            index = ' '.join((args['index'], args['query'], ))
        else:
            result = PackageDB.get_repo_list(quiet=True)

    elif index == AUR:
        if args['queries']:
            result = MultipleTasksExecutor({
                AUR+search_word: AurTaskWorkerSearch(search_query=search_word)
                for search_word in args['queries']
            }).execute()
            if args['namesonly']:
                for subindex, subresult in result.items():
                    result[subindex] = [
                        pkg for pkg in subresult
                        if subindex.split(AUR)[1] in pkg.name
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

    if not args.get('quiet'):
        sys.stderr.write('#')
        sys.stderr.flush()
    return index, result


def join_search_results(all_aur_results):
    aur_pkgs_nameset = None
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


def print_package_search_results(packages, local_pkgs_versions, args):
    def get_sort_key(pkg):
        if getattr(pkg, "numvotes", None):
            return (pkg.numvotes + 0.1) * (pkg.popularity + 0.1)
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
            if getattr(package, 'db', None):
                repo = pretty_format_repo_name(package.db.name)

            groups = ''
            if getattr(package, 'groups', None):
                groups = color_line('({}) '.format(' '.join(package.groups)), 4)

            installed = ''
            if pkg_name in local_pkgs_names:
                installed = color_line('[installed{}] '.format(
                    f': {local_pkgs_versions[pkg_name]}'
                    if package.version != local_pkgs_versions[pkg_name]
                    else ''
                ), 14)

            rating = ''
            if getattr(package, "numvotes", None):
                rating = color_line('({}, {:.2f})'.format(
                    package.numvotes,
                    package.popularity
                ), 3)

            print("{}{} {} {}{}{}".format(
                repo,
                bold_line(pkg_name),
                color_line(package.version, 10),
                groups,
                installed,
                rating
            ))
            print(format_paragraph(f'{package.desc}'))


def cli_search_packages(args):
    search_query = args.positional or []
    REPO_ONLY = False  # pylint: disable=invalid-name
    AUR_ONLY = False  # pylint: disable=invalid-name
    if not args.quiet:
        progressbar_length = max(len(search_query), 1) + (not REPO_ONLY) + (not AUR_ONLY)
        sys.stderr.write('Searching... [' + '-' * progressbar_length + ']')
        sys.stderr.write(f'{(chr(27))}[\bb' * (progressbar_length + 1))
        sys.stderr.flush()
    with ThreadPool() as pool:
        results = pool.map(package_search_worker, [
            {
                "index": LOCAL,
                "quiet": args.quiet,
            }
        ] + (
            [
                {
                    "index": REPO,
                    "query": search_word,
                    "namesonly": args.namesonly,
                    "quiet": args.quiet,
                }
                for search_word in search_query or ['']
            ] if not AUR_ONLY
            else []
        ) + (
            [
                {
                    "index": AUR,
                    "queries": search_query,
                    "namesonly": args.namesonly,
                    "quiet": args.quiet,
                }
            ] if not REPO_ONLY
            else []
        ))
    result = dict(results)
    if not args.quiet:
        sys.stderr.write('\n')

    local_pkgs_versions = result[LOCAL]
    if not AUR_ONLY:
        repo_result = join_search_results([r for k, r in result.items() if k.startswith(REPO)])
        print_package_search_results(
            packages=repo_result,
            local_pkgs_versions=local_pkgs_versions,
            args=args
        )
    if not REPO_ONLY:
        aur_result = join_search_results([r for k, r in result[AUR].items()])
        print_package_search_results(
            packages=aur_result,
            local_pkgs_versions=local_pkgs_versions,
            args=args
        )
