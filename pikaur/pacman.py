from typing import List, Dict

from pycman.config import PacmanConfig as PycmanConfig
import pyalpm

from .core import (
    DataType, CmdTaskWorker, PackageSource,
)
from .i18n import _
from .version import (
    get_package_name_and_version_matcher_from_depend_line,
    VersionMatcher,
)
from .pprint import print_status_message


OFFICIAL_REPOS = (
    'testing',
    'core',
    'extra',
    'community-testing',
    'community',
    'multilib-testing',
    'multilib',
)


class PacmanConfig(PycmanConfig):

    def __init__(self):
        super().__init__('/etc/pacman.conf')


class PacmanTaskWorker(CmdTaskWorker):

    def __init__(self, args: List[str]) -> None:
        super().__init__(
            [
                "pacman",
            ] + args
        )


class PacmanColorTaskWorker(PacmanTaskWorker):

    def __init__(self, args: List[str]) -> None:
        super().__init__(
            [
                "--color=always",
            ] + args
        )


class ProvidedDependency(DataType):
    name: str = None
    package: pyalpm.Package = None
    version_matcher: VersionMatcher = None


class PackageDBCommon():

    _packages_list_cache: Dict[PackageSource, List[pyalpm.Package]] = {}
    _packages_dict_cache: Dict[PackageSource, Dict[str, pyalpm.Package]] = {}
    _provided_list_cache: Dict[PackageSource, List[str]] = {}
    _provided_dict_cache: Dict[PackageSource, Dict[str, List[ProvidedDependency]]] = {}

    @classmethod
    def get_repo_list(cls, **kwargs):
        if not cls._packages_list_cache.get(PackageSource.REPO):
            cls._packages_list_cache[PackageSource.REPO] = list(
                cls.get_repo_dict(**kwargs).values()
            )
        return cls._packages_list_cache[PackageSource.REPO]

    @classmethod
    def get_local_list(cls, **kwargs):
        if not cls._packages_list_cache.get(PackageSource.LOCAL):
            cls._packages_list_cache[PackageSource.LOCAL] = list(
                cls.get_local_dict(**kwargs).values()
            )
        return cls._packages_list_cache[PackageSource.LOCAL]

    @classmethod
    def get_repo_dict(cls, **kwargs):
        if not cls._packages_dict_cache.get(PackageSource.REPO):
            cls._packages_dict_cache[PackageSource.REPO] = {
                pkg.name: pkg
                for pkg in cls.get_repo_list(**kwargs)
            }
        return cls._packages_dict_cache[PackageSource.REPO]

    @classmethod
    def get_local_dict(cls, **kwargs):
        if not cls._packages_dict_cache.get(PackageSource.LOCAL):
            cls._packages_dict_cache[PackageSource.LOCAL] = {
                pkg.name: pkg
                for pkg in cls.get_local_list(**kwargs)
            }
        return cls._packages_dict_cache[PackageSource.LOCAL]

    @classmethod
    def _get_provided_names(cls, package_source: PackageSource) -> List[str]:
        if not cls._provided_list_cache.get(package_source):
            cls._provided_list_cache[package_source] = [
                provided_pkg.name
                for provided_pkgs in cls._get_provided_dict(package_source).values()
                for provided_pkg in provided_pkgs
            ]
        return cls._provided_list_cache[package_source]

    @classmethod
    def get_repo_provided_names(cls) -> List[str]:
        return cls._get_provided_names(PackageSource.REPO)

    @classmethod
    def get_local_provided_names(cls) -> List[str]:
        return cls._get_provided_names(PackageSource.LOCAL)

    @classmethod
    def _get_provided_dict(
            cls, package_source: PackageSource
    ) -> Dict[str, List[ProvidedDependency]]:

        if not cls._provided_dict_cache.get(package_source):
            provided_pkg_names: Dict[str, List[ProvidedDependency]] = {}
            for pkg in (
                    cls.get_local_list() if package_source == PackageSource.LOCAL
                    else cls.get_repo_list()
            ):
                if pkg.provides:
                    for provided_pkg in pkg.provides:
                        provided_name, version_matcher = \
                            get_package_name_and_version_matcher_from_depend_line(
                                provided_pkg
                            )
                        provided_pkg_names.setdefault(pkg.name, []).append(
                            ProvidedDependency(
                                name=provided_name,
                                package=pkg,
                                version_matcher=version_matcher
                            )
                        )
            cls._provided_dict_cache[package_source] = provided_pkg_names
        return cls._provided_dict_cache[package_source]

    @classmethod
    def get_repo_provided_dict(cls) -> Dict[str, List[ProvidedDependency]]:
        return cls._get_provided_dict(PackageSource.REPO)

    @classmethod
    def get_local_provided_dict(cls) -> Dict[str, List[ProvidedDependency]]:
        return cls._get_provided_dict(PackageSource.LOCAL)


class RepositoryNotFound(Exception):
    pass


class PackageDB(PackageDBCommon):

    _alpm_handle = None

    @classmethod
    def get_alpm_handle(cls):
        if not cls._alpm_handle:
            cls._alpm_handle = PacmanConfig().initialize_alpm()
        return cls._alpm_handle

    @classmethod
    def search_local(cls, search_query):
        return cls.get_alpm_handle().get_localdb().search(search_query)

    @classmethod
    def get_local_list(cls, **kwargs):
        if not cls._packages_list_cache.get(PackageSource.LOCAL):
            if not kwargs.get('quiet'):
                print_status_message(_("Reading local package database..."))
            cls._packages_list_cache[PackageSource.LOCAL] = cls.search_local('')
        return cls._packages_list_cache[PackageSource.LOCAL]

    @classmethod
    def get_repo_priority(cls, repo_name: str):
        """
        0 is the highest priority
        """
        repos = [r.name for r in cls.get_alpm_handle().get_syncdbs()]
        if repo_name not in repos:
            raise RepositoryNotFound(f"'{repo_name}' in {repos}")
        return repos.index(repo_name)

    @classmethod
    def search_repo_dict(
            cls, search_query, db_name: str = None, names_only=False, exact_match=False
    ):
        if '/' in search_query:
            db_name, search_query = search_query.split('/')
        result = {}
        for sync_db in reversed(cls.get_alpm_handle().get_syncdbs()):
            if not db_name or db_name == sync_db.name:
                for pkg in sync_db.search(search_query):
                    if (
                            (
                                not names_only or search_query in pkg.name
                            ) and (
                                not exact_match or search_query == pkg.name
                            )
                    ):
                        result[pkg.name] = pkg
        return result

    @classmethod
    def search_repo(cls, *args, **kwargs):
        return list(
            cls.search_repo_dict(*args, **kwargs).values()
        )

    @classmethod
    def get_repo_dict(cls, **kwargs):
        if not cls._packages_dict_cache.get(PackageSource.REPO):
            if not kwargs.get('quiet'):
                print_status_message(_("Reading repository package databases..."))
            cls._packages_dict_cache[PackageSource.REPO] = cls.search_repo_dict('')
        return cls._packages_dict_cache[PackageSource.REPO]


def find_repo_packages(package_names):
    pacman_packages = []
    not_found_packages = []
    for package_name in package_names:
        search_results = PackageDB.search_repo(package_name, exact_match=True)
        if search_results:
            pacman_packages.append(search_results[0])
        else:
            not_found_packages.append(package_name)
    return pacman_packages, not_found_packages


def find_local_packages(package_names):
    all_local_pkgs = PackageDB.get_local_dict()
    pacman_packages = []
    not_found_packages = []
    for package_name in package_names:
        if all_local_pkgs.get(package_name):
            pacman_packages.append(all_local_pkgs[package_name])
        else:
            not_found_packages.append(package_name)
    return pacman_packages, not_found_packages


def find_packages_not_from_repo():
    local_pkg_names = PackageDB.get_local_dict().keys()
    repo_pkg_names = PackageDB.get_repo_dict().keys()
    not_found_packages = []
    for pkg_name in local_pkg_names:
        if pkg_name not in repo_pkg_names:
            not_found_packages.append(pkg_name)
    return not_found_packages
