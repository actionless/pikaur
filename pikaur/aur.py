import os
import gzip
import json
from multiprocessing.pool import ThreadPool
from urllib import parse, request
from urllib.parse import quote
from typing import List, Dict, Tuple, Union, Any

from .core import DataType, get_chunks
from .exceptions import AURError


AUR_HOST = 'aur.archlinux.org'
AUR_BASE_URL = 'https://' + AUR_HOST


class AURPackageInfo(DataType):
    name: str = None
    version: str = None
    desc: str = None
    numvotes: int = None
    popularity: float = None
    depends: List[str] = None
    makedepends: List[str] = None
    conflicts: List[str] = None
    replaces: List[str] = None

    id: str = None  # pylint: disable=invalid-name
    packagebaseid: str = None
    packagebase: str = None
    url: str = None
    outofdate: int = None
    maintainer: str = None
    firstsubmitted: int = None
    lastmodified: int = None
    urlpath: str = None
    optdepends: List[str] = None
    provides: List[str] = None
    license: str = None
    keywords: List[str] = None
    groups: List[str] = None
    checkdepends: List[str] = None

    def __init__(self, **kwargs):
        if 'description' in kwargs:
            kwargs['desc'] = kwargs.pop('description')
        super().__init__(**kwargs)


def read_bytes_from_url(url: str) -> bytes:
    req = request.Request(url)
    last_proxy_params: Tuple[str, str] = None
    for proxy_env_var in ('http_proxy', 'https_proxy'):
        if proxy_env_var not in os.environ:
            continue
        try:
            proxy_url = parse.urlparse(os.environ[proxy_env_var])
        except Exception:
            pass
        else:
            last_proxy_params = (
                proxy_url.netloc or proxy_url.path,
                proxy_url.scheme or proxy_env_var.split('_')[0]
            )
    if last_proxy_params:
        req.set_proxy(*last_proxy_params)
    response = request.urlopen(req)
    result_bytes = response.read()
    return result_bytes


def get_json_from_url(url: str) -> Dict[str, Any]:
    result_bytes = read_bytes_from_url(url)
    result_json = json.loads(result_bytes.decode('utf-8'))
    if 'error' in result_json:
        raise AURError(result_json['error'])
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


def aur_rpc_search_name_desc(search_query: str) -> List[AURPackageInfo]:
    result_json = get_json_from_url(
        construct_aur_rpc_url_from_params({
            'v': 5,
            'type': 'search',
            'arg': search_query,
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
        uri += '&arg[]=' + quote(package)
    result_json = get_json_from_url(
        construct_aur_rpc_url_from_uri(uri)
    )
    return [
        AURPackageInfo(**{key.lower(): value for key, value in aur_json.items()})
        for aur_json in result_json.get('results', [])
    ]


def aur_web_packages_list():
    return get_gzip_from_url(AUR_BASE_URL + '/packages.gz').splitlines()[1:]


_AUR_PKGS_FIND_CACHE: Dict[str, AURPackageInfo] = {}


def find_aur_packages(package_names: List[str]) -> Tuple[List[AURPackageInfo], List[str]]:

    # @TODO: return only packages for the current architecture
    package_names = list(package_names)[:]
    json_results = []
    for package_name in package_names[:]:
        aur_pkg = _AUR_PKGS_FIND_CACHE.get(package_name)
        if aur_pkg:
            json_results.append(aur_pkg)
            package_names.remove(package_name)

    if package_names:
        with ThreadPool() as pool:
            results = pool.map(aur_rpc_info, get_chunks(package_names, chunk_size=200))
        for result in results:
            for aur_pkg in result:
                _AUR_PKGS_FIND_CACHE[aur_pkg.name] = aur_pkg
                json_results.append(aur_pkg)

    found_aur_packages = [
        result.name for result in json_results
    ]
    not_found_packages: List[str] = []
    if len(package_names) != len(found_aur_packages):
        not_found_packages = [
            package for package in package_names
            if package not in found_aur_packages
        ]

    return json_results, not_found_packages


def get_repo_url(package_base_name: str) -> str:
    return f'https://aur.archlinux.org/{package_base_name}.git'


_AUR_PKGS_LIST_CACHE: List[str] = None


def get_all_aur_names() -> List[str]:
    global _AUR_PKGS_LIST_CACHE  # pylint: disable=global-statement
    if not _AUR_PKGS_LIST_CACHE:
        _AUR_PKGS_LIST_CACHE = aur_web_packages_list()
    return _AUR_PKGS_LIST_CACHE


def get_all_aur_packages() -> List[AURPackageInfo]:
    return find_aur_packages(get_all_aur_names())[0]
