""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import gzip
import json
from multiprocessing.pool import ThreadPool
from urllib import parse, request
from urllib.parse import quote
from urllib.error import URLError
from typing import List, Dict, Tuple, Union, Any, Optional

from .i18n import _
from .core import DataType, get_chunks
from .exceptions import AURError, SysExit
from .progressbar import ThreadSafeProgressBar
from .pprint import print_error
from .prompt import ask_to_continue
from .config import PikaurConfig


AUR_HOST = PikaurConfig().misc.AurHost.get_str()
AUR_BASE_URL = 'https://' + AUR_HOST


class AURPackageInfo(DataType):
    packagebase: str
    name: str
    version: str
    desc: Optional[str] = None
    numvotes: Optional[int] = None
    popularity: Optional[float] = None
    depends: List[str] = []
    makedepends: List[str] = []
    optdepends: List[str] = []
    checkdepends: List[str] = []
    conflicts: List[str] = []
    replaces: List[str] = []
    provides: List[str] = []

    id: Optional[str] = None  # pylint: disable=invalid-name
    packagebaseid: Optional[str] = None
    url: Optional[str] = None
    outofdate: Optional[int] = None
    maintainer: Optional[str] = None
    firstsubmitted: Optional[int] = None
    lastmodified: Optional[int] = None
    urlpath: Optional[str] = None
    license: Optional[str] = None
    keywords: List[str] = []
    groups: List[str] = []

    @property
    def git_url(self) -> str:
        return f'{AUR_BASE_URL}/{self.packagebase}.git'

    def __init__(self, **kwargs) -> None:
        if 'description' in kwargs:
            kwargs['desc'] = kwargs.pop('description')
        super().__init__(**kwargs)

    @classmethod
    def from_srcinfo(cls, srcinfo) -> 'AURPackageInfo':
        return cls(
            name=srcinfo.package_name,
            version=srcinfo.get_value('pkgver') + '-' + srcinfo.get_value('pkgrel'),
            desc=srcinfo.get_value('pkgdesc'),
            packagebase=srcinfo.get_value('pkgbase'),
            **{
                key: srcinfo.get_values(key)
                for key in [
                    'depends',
                    'makedepends',
                    'optdepends',
                    'checkdepends',
                    'conflicts',
                    'replaces',
                    'provides',
                ]
            }
        )


def read_bytes_from_url(url: str) -> bytes:
    req = request.Request(url)
    try:
        response = request.urlopen(req)
    except URLError as exc:
        print_error('urllib: ' + str(exc.reason))
        if ask_to_continue(_('Do you want to retry?')):
            return read_bytes_from_url(url)
        raise SysExit(102)
    result_bytes = response.read()
    return result_bytes


def get_json_from_url(url: str) -> Dict[str, Any]:
    result_bytes = read_bytes_from_url(url)
    result_json = json.loads(result_bytes.decode('utf-8'))
    if 'error' in result_json:
        raise AURError(url=url, error=result_json['error'])
    return result_json


def get_gzip_from_url(url: str) -> str:
    result_bytes = read_bytes_from_url(url)
    decompressed_bytes_response = gzip.decompress(result_bytes)
    text_response = decompressed_bytes_response.decode('utf-8')
    return text_response


def construct_aur_rpc_url_from_uri(uri: str) -> str:
    url = AUR_BASE_URL + '/rpc/?' + uri
    return url


def construct_aur_rpc_url_from_params(params: Dict[str, Union[str, int]]) -> str:
    uri = parse.urlencode(params)
    return construct_aur_rpc_url_from_uri(uri)


def strip_aur_repo_name(pkg_name: str) -> str:
    if pkg_name.startswith('aur/'):
        pkg_name = ''.join(pkg_name.split('aur/'))
    return pkg_name


def aur_rpc_search_name_desc(search_query: str) -> List[AURPackageInfo]:
    result_json = get_json_from_url(
        construct_aur_rpc_url_from_params({
            'v': 5,
            'type': 'search',
            'arg': strip_aur_repo_name(search_query),
            'by': 'name-desc'
        })
    )
    return [
        AURPackageInfo(**{key.lower(): value for key, value in aur_json.items()})
        for aur_json in result_json.get('results', [])
    ]


def aur_rpc_info(search_queries: List[str]) -> List[AURPackageInfo]:
    uri = parse.urlencode({
        'v': 5,
        'type': 'info',
    })
    for package in search_queries:
        uri += '&arg[]=' + quote(strip_aur_repo_name(package))
    result_json = get_json_from_url(
        construct_aur_rpc_url_from_uri(uri)
    )
    return [
        AURPackageInfo(**{key.lower(): value for key, value in aur_json.items()})
        for aur_json in result_json.get('results', [])
    ]


def aur_rpc_info_with_progress(
        args: Tuple[List[str], int, bool]
) -> List[AURPackageInfo]:
    search_queries, progressbar_length, with_progressbar = args
    result = aur_rpc_info(search_queries)
    if with_progressbar:
        progressbar = ThreadSafeProgressBar.get(
            progressbar_length=progressbar_length,
            progressbar_id='aur_search',
        )
        progressbar.update()
    return result


def aur_web_packages_list() -> List[str]:
    return get_gzip_from_url(AUR_BASE_URL + '/packages.gz').splitlines()[1:]


_AUR_PKGS_FIND_CACHE: Dict[str, AURPackageInfo] = {}


def find_aur_packages(
        package_names: List[str], with_progressbar=False
) -> Tuple[List[AURPackageInfo], List[str]]:

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
                    _AUR_PKGS_FIND_CACHE[aur_pkg.name] = aur_pkg  # type: ignore
                    json_results.append(aur_pkg)  # type: ignore

    found_aur_packages = [
        result.name for result in json_results
    ]
    not_found_packages: List[str] = []
    if num_packages != len(found_aur_packages):
        not_found_packages = [
            package for package in package_names
            if package not in found_aur_packages
        ]

    return json_results, not_found_packages


def get_repo_url(package_base_name: str) -> str:
    return f'https://aur.archlinux.org/{package_base_name}.git'


_AUR_PKGS_LIST_CACHE: List[str] = []


def get_all_aur_names() -> List[str]:
    global _AUR_PKGS_LIST_CACHE  # pylint: disable=global-statement
    if not _AUR_PKGS_LIST_CACHE:
        _AUR_PKGS_LIST_CACHE = aur_web_packages_list()
    return _AUR_PKGS_LIST_CACHE


def get_all_aur_packages() -> List[AURPackageInfo]:
    return find_aur_packages(get_all_aur_names(), with_progressbar=True)[0]
