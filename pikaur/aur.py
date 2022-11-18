"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

from multiprocessing.pool import ThreadPool
from typing import TYPE_CHECKING
from urllib import parse
from urllib.parse import quote

from .config import PikaurConfig
from .core import DataType, get_chunks
from .exceptions import AURError
from .progressbar import ThreadSafeProgressBar
from .urllib import get_gzip_from_url, get_json_from_url
if TYPE_CHECKING:
    from .srcinfo import SrcInfo


AUR_BASE_URL = PikaurConfig().network.AurUrl.get_str()


class AURPackageInfo(DataType):
    packagebase: str
    name: str
    version: str
    desc: str | None = None
    numvotes: int | None = None
    popularity: float | None = None
    depends: list[str] = []
    makedepends: list[str] = []
    optdepends: list[str] = []
    checkdepends: list[str] = []
    conflicts: list[str] = []
    replaces: list[str] = []
    provides: list[str] = []

    aur_id: str | None = None
    packagebaseid: str | None = None
    url: str | None = None
    outofdate: int | None = None
    maintainer: str | None = None
    firstsubmitted: int | None = None
    lastmodified: int | None = None
    urlpath: str | None = None
    pkg_license: str | None = None
    keywords: list[str] = []
    groups: list[str] = []

    @property
    def git_url(self) -> str:
        return f'{AUR_BASE_URL}/{self.packagebase}.git'

    # @TODO: type it later:
    def __init__(self, **kwargs) -> None:  # type: ignore
        for aur_api_name, pikaur_class_name in (
            ('description', 'desc', ),
            ('id', 'aur_id', ),
            ('license', 'pkg_license', ),
        ):
            if aur_api_name in kwargs:
                kwargs[pikaur_class_name] = kwargs.pop(aur_api_name)
        super().__init__(**kwargs)

    @classmethod
    def from_srcinfo(cls, srcinfo: 'SrcInfo') -> 'AURPackageInfo':
        return cls(
            name=srcinfo.package_name,
            version=(srcinfo.get_value('pkgver') or '') + '-' + (srcinfo.get_value('pkgrel') or ''),
            desc=srcinfo.get_value('pkgdesc'),
            packagebase=srcinfo.get_value('pkgbase'),
            depends=[dep.line for dep in srcinfo.get_depends().values()],
            makedepends=[dep.line for dep in srcinfo.get_build_makedepends().values()],
            checkdepends=[dep.line for dep in srcinfo.get_build_checkdepends().values()],
            **{
                key: srcinfo.get_values(key)
                for key in [
                    'optdepends',
                    'conflicts',
                    'replaces',
                    'provides',
                ]
            }
        )

    def __repr__(self) -> str:
        return (
            f'<{self.__class__.__name__} "{self.name}" '
            f'{self.version}>'
        )


def construct_aur_rpc_url_from_uri(uri: str) -> str:
    url = AUR_BASE_URL + '/rpc/?' + uri
    return url


def construct_aur_rpc_url_from_params(params: dict[str, str | int]) -> str:
    uri = parse.urlencode(params)
    return construct_aur_rpc_url_from_uri(uri)


def strip_aur_repo_name(pkg_name: str) -> str:
    if pkg_name.startswith('aur/'):
        pkg_name = ''.join(pkg_name.split('aur/'))
    return pkg_name


def aur_rpc_search_name_desc(search_query: str) -> list[AURPackageInfo]:
    url = construct_aur_rpc_url_from_params({
        'v': 5,
        'type': 'search',
        'arg': strip_aur_repo_name(search_query),
        'by': 'name-desc'
    })
    result_json = get_json_from_url(url)
    if 'error' in result_json:
        raise AURError(url=url, error=result_json['error'])
    return [
        AURPackageInfo(**{key.lower(): value for key, value in aur_json.items()})
        for aur_json in result_json.get('results', [])
    ]


def aur_rpc_info(search_queries: list[str]) -> list[AURPackageInfo]:
    uri = parse.urlencode({
        'v': 5,
        'type': 'info',
    })
    for package in search_queries:
        uri += '&arg[]=' + quote(strip_aur_repo_name(package))
    url = construct_aur_rpc_url_from_uri(uri)
    result_json = get_json_from_url(url)
    if 'error' in result_json:
        raise AURError(url=url, error=result_json['error'])
    return [
        AURPackageInfo(**{key.lower(): value for key, value in aur_json.items()})
        for aur_json in result_json.get('results', [])
    ]


def aur_rpc_info_with_progress(
        args: tuple[list[str], int, bool]
) -> list[AURPackageInfo]:
    search_queries, progressbar_length, with_progressbar = args
    result = aur_rpc_info(search_queries)
    if with_progressbar:
        progressbar = ThreadSafeProgressBar.get(
            progressbar_length=progressbar_length,
            progressbar_id='aur_search',
        )
        progressbar.update()
    return result


def aur_web_packages_list() -> list[str]:
    return get_gzip_from_url(AUR_BASE_URL + '/packages.gz').splitlines()[1:]


_AUR_PKGS_FIND_CACHE: dict[str, AURPackageInfo] = {}


def find_aur_packages(
        package_names: list[str], with_progressbar: bool = False
) -> tuple[list[AURPackageInfo], list[str]]:

    # @TODO: return only packages for the current architecture
    package_names = [strip_aur_repo_name(name) for name in package_names]
    num_packages = len(package_names)
    json_results = []
    for package_name in package_names[:]:
        aur_pkg = _AUR_PKGS_FIND_CACHE.get(package_name)
        if aur_pkg:
            json_results.append(aur_pkg)
            package_names.remove(package_name)

    if package_names:
        with ThreadPool() as pool:
            search_chunks = list(get_chunks(package_names, chunk_size=200))
            requests = [
                pool.apply_async(aur_rpc_info_with_progress, [
                    (chunk, len(search_chunks), with_progressbar, )
                ])
                for chunk in search_chunks
            ]
            pool.close()
            results = [request.get() for request in requests]
            pool.join()
            for result in results:
                for aur_pkg in result:
                    _AUR_PKGS_FIND_CACHE[aur_pkg.name] = aur_pkg
                    if aur_pkg.name in package_names:
                        json_results.append(aur_pkg)

    found_aur_packages = [
        result.name for result in json_results
    ]
    not_found_packages: list[str] = (
        [] if num_packages == len(found_aur_packages)
        else [
            package for package in package_names
            if package not in found_aur_packages
        ]
    )
    return json_results, not_found_packages


def get_repo_url(package_base_name: str) -> str:
    return f'{AUR_BASE_URL}/{package_base_name}.git'


_AUR_PKGS_LIST_CACHE: list[str] = []


def get_all_aur_names() -> list[str]:
    global _AUR_PKGS_LIST_CACHE  # pylint: disable=global-statement
    if not _AUR_PKGS_LIST_CACHE:
        _AUR_PKGS_LIST_CACHE = aur_web_packages_list()
    return _AUR_PKGS_LIST_CACHE


def get_all_aur_packages() -> list[AURPackageInfo]:
    return find_aur_packages(get_all_aur_names(), with_progressbar=True)[0]
