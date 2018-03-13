import asyncio
from urllib.parse import urlencode, quote
from typing import List, Dict, Awaitable, Tuple

from .i18n import _
from .core import DataType, get_chunks
from .async import SingleTaskExecutor, MultipleTasksExecutorPool, TaskWorker
from .async_net import (
    https_client_task, NetworkTaskResultJSON, NetworkTaskResultGzip
)


AUR_HOST = 'aur.archlinux.org'


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


class AURTaskWorker(TaskWorker):
    uri: str = None
    params: str = None

    async def aur_client_task(self, loop: asyncio.AbstractEventLoop) -> List[AURPackageInfo]:
        raw_result = await https_client_task(
            loop, AUR_HOST, self.uri, result_class=NetworkTaskResultJSON
        )
        if not isinstance(raw_result, NetworkTaskResultJSON):
            raise RuntimeError
        return [
            AURPackageInfo(**{key.lower(): value for key, value in aur_json.items()})
            for aur_json in raw_result.json.get('results', [])
        ]

    def get_task(self, loop: asyncio.AbstractEventLoop) -> Awaitable[List[AURPackageInfo]]:
        self.uri = f'/rpc/?{self.params}'
        return self.aur_client_task(loop)


class AURTaskWorkerSearch(AURTaskWorker):

    def __init__(self, search_query: str) -> None:
        self.params = urlencode({
            'v': 5,
            'type': 'search',
            'arg': search_query,
            'by': 'name-desc'
        })


class AURTaskWorkerInfo(AURTaskWorker):

    def __init__(self, packages: List[str]) -> None:
        self.params = urlencode({
            'v': 5,
            'type': 'info',
        })
        for package in packages:
            self.params += '&arg[]=' + quote(package)


class AURTaskWorkerList(TaskWorker):

    uri = '/packages.gz'

    async def aur_client_task(self, loop: asyncio.AbstractEventLoop) -> List[str]:
        raw_result = await https_client_task(
            loop, AUR_HOST, self.uri, result_class=NetworkTaskResultGzip
        )
        if not isinstance(raw_result, NetworkTaskResultGzip):
            raise RuntimeError
        return [
            pkg_name for pkg_name in raw_result.text.split('\n')
            if pkg_name
        ][1:]

    def get_task(self, loop: asyncio.AbstractEventLoop) -> Awaitable[List[str]]:
        return self.aur_client_task(loop)


_AUR_PKGS_FIND_CACHE: Dict[str, AURPackageInfo] = {}


def find_aur_packages(
        package_names: List[str], enable_progressbar=False
) -> Tuple[List[AURPackageInfo], List[str]]:

    # @TODO: return only packages for the current architecture
    package_names = list(package_names)[:]
    json_results = []
    for package_name in package_names[:]:
        aur_pkg = _AUR_PKGS_FIND_CACHE.get(package_name)
        if aur_pkg:
            json_results.append(aur_pkg)
            package_names.remove(package_name)

    if package_names:
        results = MultipleTasksExecutorPool(
            {
                str(_id): AURTaskWorkerInfo(packages=packages_chunk)
                for _id, packages_chunk in enumerate(
                    # get_chunks(package_names, chunk_size=100)
                    get_chunks(package_names, chunk_size=200)
                )
            },
            pool_size=8,
            enable_progressbar=enable_progressbar
        ).execute()

        for result in results.values():
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


def get_repo_url(package_name: str) -> str:
    package_base_name = find_aur_packages([package_name])[0][0].packagebase
    return f'https://aur.archlinux.org/{package_base_name}.git'


_AUR_PKGS_LIST_CACHE: List[str] = None


def get_all_aur_names() -> List[str]:
    global _AUR_PKGS_LIST_CACHE  # pylint: disable=global-statement
    if not _AUR_PKGS_LIST_CACHE:
        _AUR_PKGS_LIST_CACHE = SingleTaskExecutor(
            AURTaskWorkerList()
        ).execute()
    return _AUR_PKGS_LIST_CACHE


def get_all_aur_packages() -> List[AURPackageInfo]:
    return find_aur_packages(
        get_all_aur_names(),
        enable_progressbar=_("Getting ALL AUR info") + " "
    )[0]
