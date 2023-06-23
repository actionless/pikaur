"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

from multiprocessing.pool import ThreadPool
from typing import TYPE_CHECKING, ClassVar
from urllib import parse
from urllib.parse import quote

from .config import PikaurConfig
from .core import DataType
from .exceptions import AURError
from .progressbar import ThreadSafeProgressBar
from .urllib import get_gzip_from_url, get_json_from_url

if TYPE_CHECKING:
    from typing import Any, Final

    from .srcinfo import SrcInfo


MAX_URL_LENGTH: "Final" = 8177  # default value in many web servers


class AurRPCErrors:
    ERROR_KEY: "Final" = "error"
    TOO_MANY_RESULTS: "Final" = "Too many package results."
    QUERY_TOO_SMALL: "Final" = "Query arg too small."


class AurBaseUrl:
    aur_base_url: str | None = None

    @classmethod
    def get(cls) -> str:
        if not cls.aur_base_url:
            cls.aur_base_url = PikaurConfig().network.AurUrl.get_str()
        return cls.aur_base_url


class AURPackageInfo(DataType):
    packagebase: str
    name: str
    version: str
    desc: str | None = None
    numvotes: int | None = None
    popularity: float | None = None
    depends: list[str]
    makedepends: list[str]
    optdepends: list[str]
    checkdepends: list[str]
    conflicts: list[str]
    replaces: list[str]
    provides: list[str]

    aur_id: str | None = None
    packagebaseid: str | None = None
    url: str | None = None
    outofdate: int | None = None
    maintainer: str | None = None
    firstsubmitted: int | None = None
    lastmodified: int | None = None
    urlpath: str | None = None
    pkg_license: str | None = None
    keywords: list[str]
    groups: list[str]
    submitter: str | None = None
    comaintainers: list[str]

    @property
    def git_url(self) -> str:
        return f"{AurBaseUrl.get()}/{self.packagebase}.git"

    def __init__(self, **kwargs: "Any") -> None:
        for aur_api_name, pikaur_class_name in (
            ("description", "desc"),
            ("id", "aur_id"),
            ("license", "pkg_license"),
        ):
            if aur_api_name in kwargs:
                kwargs[pikaur_class_name] = kwargs.pop(aur_api_name)
        for key in (
            "depends",
            "makedepends",
            "optdepends",
            "checkdepends",
            "conflicts",
            "replaces",
            "provides",
            "keywords",
            "groups",
            "comaintainers",
        ):
            kwargs.setdefault(key, [])
        super().__init__(**kwargs)

    @classmethod
    def from_srcinfo(cls, srcinfo: "SrcInfo") -> "AURPackageInfo":
        return cls(
            name=srcinfo.package_name,
            version=(srcinfo.get_value("pkgver") or "") + "-" + (srcinfo.get_value("pkgrel") or ""),
            desc=srcinfo.get_value("pkgdesc"),
            packagebase=srcinfo.get_value("pkgbase"),
            depends=[dep.line for dep in srcinfo.get_depends().values()],
            makedepends=[dep.line for dep in srcinfo.get_build_makedepends().values()],
            checkdepends=[dep.line for dep in srcinfo.get_build_checkdepends().values()],
            **{
                key: srcinfo.get_values(key)
                for key in [
                    "optdepends",
                    "conflicts",
                    "replaces",
                    "provides",
                ]
            },
        )

    def __repr__(self) -> str:
        return (
            f'<{self.__class__.__name__} "{self.name}" '
            f"{self.version}>"
        )


def construct_aur_rpc_url_from_uri(uri: str) -> str:
    return AurBaseUrl.get() + "/rpc/?" + uri


def construct_aur_rpc_url_from_params(params: dict[str, str | int]) -> str:
    return construct_aur_rpc_url_from_uri(parse.urlencode(params))


def strip_aur_repo_name(pkg_name: str) -> str:
    if pkg_name.startswith("aur/"):
        return "".join(pkg_name.split("aur/"))
    return pkg_name


def aur_rpc_search_name_desc(search_query: str) -> list[AURPackageInfo]:
    url = construct_aur_rpc_url_from_params({
        "v": 5,
        "type": "search",
        "arg": strip_aur_repo_name(search_query),
        "by": "name-desc",
    })
    result_json = get_json_from_url(url)
    if AurRPCErrors.ERROR_KEY in result_json:
        raise AURError(url=url, error=result_json[AurRPCErrors.ERROR_KEY])
    return [
        AURPackageInfo(
            **{key.lower(): value for key, value in aur_json.items()},
            ignore_extra_properties=True,
        )
        for aur_json in result_json.get("results", [])
    ]


def _get_aur_rpc_info_url(search_queries: list[str]) -> str:
    uri = parse.urlencode({
        "v": 5,
        "type": "info",
    })
    for package in search_queries:
        uri += "&arg[]=" + quote(strip_aur_repo_name(package))
    return construct_aur_rpc_url_from_uri(uri)


def aur_rpc_info(search_queries: list[str]) -> list[AURPackageInfo]:
    url = _get_aur_rpc_info_url(search_queries=search_queries)
    result_json = get_json_from_url(url)
    if AurRPCErrors.ERROR_KEY in result_json:
        raise AURError(url=url, error=result_json[AurRPCErrors.ERROR_KEY])
    return [
        AURPackageInfo(
            **{key.lower(): value for key, value in aur_json.items()},
            ignore_extra_properties=True,
        )
        for aur_json in result_json.get("results", [])
    ]


def aur_rpc_info_with_progress(
        search_queries: list[str], *, progressbar_length: int, with_progressbar: bool,
) -> list[AURPackageInfo]:
    result = aur_rpc_info(search_queries)
    if with_progressbar:
        progressbar = ThreadSafeProgressBar.get(
            progressbar_length=progressbar_length,
            progressbar_id="aur_search",
        )
        progressbar.update()
    return result


class AurPackageListCache:

    cache: ClassVar[list[str]] = []

    @classmethod
    def get(cls) -> list[str]:
        if not cls.cache:
            cls.cache = get_gzip_from_url(AurBaseUrl.get() + "/packages.gz").splitlines()[1:]
        return cls.cache


class AurPackageSearchCache:

    cache: ClassVar[dict[str, AURPackageInfo]] = {}

    @classmethod
    def put(cls, pkg: AURPackageInfo) -> None:
        cls.cache[pkg.name] = pkg

    @classmethod
    def get(cls, pkg_name: str) -> AURPackageInfo | None:
        return cls.cache.get(pkg_name)


def get_all_aur_names() -> list[str]:
    return AurPackageListCache.get()


def get_max_pkgs_chunks(package_names: list[str]) -> list[list[str]]:
    chunks = []
    chunk: list[str] = []
    pkgs_to_do = package_names[::]
    while pkgs_to_do:
        if len(_get_aur_rpc_info_url([*chunk, pkgs_to_do[0]])) < MAX_URL_LENGTH:
            chunk.append(pkgs_to_do.pop(0))
        else:
            chunks.append(chunk)
            chunk = []
    if chunk:
        chunks.append(chunk)
    return chunks


def find_aur_packages(
        package_names: list[str], *, with_progressbar: bool = False,
) -> tuple[list[AURPackageInfo], list[str]]:

    # @TODO: return only packages for the current architecture
    package_names = [strip_aur_repo_name(name) for name in package_names]
    num_packages = len(package_names)
    json_results = []
    for package_name in package_names[:]:
        aur_pkg = AurPackageSearchCache.get(package_name)
        if aur_pkg:
            json_results.append(aur_pkg)
            package_names.remove(package_name)

    if package_names:
        with ThreadPool() as pool:
            search_chunks = get_max_pkgs_chunks(package_names)
            requests = [
                pool.apply_async(aur_rpc_info_with_progress, [], {
                    "search_queries": chunk,
                    "progressbar_length": len(search_chunks),
                    "with_progressbar": with_progressbar,
                })
                for chunk in search_chunks
            ]
            pool.close()
            results = [request.get() for request in requests]
            pool.join()
            for result in results:
                for aur_pkg in result:
                    AurPackageSearchCache.put(aur_pkg)
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
    return f"{AurBaseUrl.get()}/{package_base_name}.git"


def get_all_aur_packages() -> list[AURPackageInfo]:
    return find_aur_packages(get_all_aur_names(), with_progressbar=True)[0]
