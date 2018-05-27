from typing import List, Dict, Tuple, Iterable, Optional, Union, TYPE_CHECKING

from pycman.config import PacmanConfig as PycmanConfig
import pyalpm

from .i18n import _
from .core import (
    DataType,
    PackageSource,
)
from .version import (
    get_package_name_and_version_matcher_from_depend_line,
    VersionMatcher,
)
from .pprint import print_status_message, color_enabled
from .args import PikaurArgs
from .config import PikaurConfig
from .exceptions import PackagesNotFoundInRepo

if TYPE_CHECKING:
    # pylint: disable=unused-import
    from .aur import AURPackageInfo  # noqa


OFFICIAL_REPOS = (
    'testing',
    'core',
    'extra',
    'community-testing',
    'community',
    'multilib-testing',
    'multilib',
)


def get_pacman_command(args: PikaurArgs) -> List[str]:
    pacman_path = PikaurConfig().misc.PacmanPath
    if color_enabled(args):
        return [pacman_path, '--color=always']
    return [pacman_path, '--color=never']


class PacmanConfig(PycmanConfig):

    def __init__(self):
        super().__init__('/etc/pacman.conf')


class ProvidedDependency(DataType):
    name: str
    package: pyalpm.Package
    version_matcher: VersionMatcher

    def __repr__(self) -> str:
        return (
            f'<{self.__class__.__name__} "{self.name}" '
            f'{self.version_matcher.line}>'
        )


def get_pkg_id(pkg: Union['AURPackageInfo', pyalpm.Package]) -> str:
    if isinstance(pkg, pyalpm.Package):
        return f"{pkg.db.name}/{pkg.name}"
    return f"aur/{pkg.name}"


class PackageDBCommon():

    _packages_list_cache: Dict[PackageSource, List[pyalpm.Package]] = {}
    _packages_dict_cache: Dict[PackageSource, Dict[str, pyalpm.Package]] = {}
    _provided_list_cache: Dict[PackageSource, List[str]] = {}
    _provided_dict_cache: Dict[PackageSource, Dict[str, List[ProvidedDependency]]] = {}

    @classmethod
    def discard_local_cache(cls) -> None:
        if cls._packages_list_cache.get(PackageSource.LOCAL):
            del cls._packages_list_cache[PackageSource.LOCAL]
        if cls._packages_dict_cache.get(PackageSource.LOCAL):
            del cls._packages_dict_cache[PackageSource.LOCAL]

    @classmethod
    def get_repo_list(cls, quiet=False) -> List[pyalpm.Package]:
        if not cls._packages_list_cache.get(PackageSource.REPO):
            cls._packages_list_cache[PackageSource.REPO] = list(
                cls.get_repo_dict(quiet=quiet).values()
            )
        return cls._packages_list_cache[PackageSource.REPO]

    @classmethod
    def get_local_list(cls, quiet=False) -> List[pyalpm.Package]:
        if not cls._packages_list_cache.get(PackageSource.LOCAL):
            cls._packages_list_cache[PackageSource.LOCAL] = list(
                cls.get_local_dict(quiet=quiet).values()
            )
        return cls._packages_list_cache[PackageSource.LOCAL]

    @classmethod
    def get_repo_dict(cls, quiet=False) -> Dict[str, pyalpm.Package]:
        if not cls._packages_dict_cache.get(PackageSource.REPO):
            cls._packages_dict_cache[PackageSource.REPO] = {
                get_pkg_id(pkg): pkg
                for pkg in cls.get_repo_list(quiet=quiet)
            }
        return cls._packages_dict_cache[PackageSource.REPO]

    @classmethod
    def get_local_dict(cls, quiet=False) -> Dict[str, pyalpm.Package]:
        if not cls._packages_dict_cache.get(PackageSource.LOCAL):
            cls._packages_dict_cache[PackageSource.LOCAL] = {
                pkg.name: pkg
                for pkg in cls.get_local_list(quiet=quiet)
            }
        return cls._packages_dict_cache[PackageSource.LOCAL]

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
                        provided_pkg_names.setdefault(provided_name, []).append(
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

    @classmethod
    def get_repo_pkgnames(cls):
        return [pkg.name for pkg in cls.get_repo_list()]

    @classmethod
    def get_local_pkgnames(cls):
        return [pkg.name for pkg in cls.get_local_list()]


class RepositoryNotFound(Exception):
    pass


class PackageDB(PackageDBCommon):

    _alpm_handle: Optional[pyalpm.Handle] = None

    @classmethod
    def get_alpm_handle(cls) -> pyalpm.Handle:
        if not cls._alpm_handle:
            cls._alpm_handle = PacmanConfig().initialize_alpm()
        return cls._alpm_handle

    @classmethod
    def discard_local_cache(cls) -> None:
        super().discard_local_cache()
        cls._alpm_handle = None

    @classmethod
    def search_local(cls, search_query: str) -> List[pyalpm.Package]:
        return cls.get_alpm_handle().get_localdb().search(search_query)

    @classmethod
    def get_local_list(cls, quiet=False) -> List[pyalpm.Package]:
        if not cls._packages_list_cache.get(PackageSource.LOCAL):
            if not quiet:
                print_status_message(_("Reading local package database..."))
            cls._packages_list_cache[PackageSource.LOCAL] = cls.search_local('')
        return cls._packages_list_cache[PackageSource.LOCAL]

    @classmethod
    def get_repo_priority(cls, repo_name: str) -> int:
        """
        0 is the highest priority
        """
        repos = [r.name for r in cls.get_alpm_handle().get_syncdbs()]
        if repo_name not in repos:
            raise RepositoryNotFound(f"'{repo_name}' in {repos}")
        return repos.index(repo_name)

    @classmethod
    def search_repo(
            cls, search_query, db_name: str = None, names_only=False, exact_match=False
    ) -> List[pyalpm.Package]:
        if '/' in search_query:
            db_name, search_query = search_query.split('/')
        result = []
        for sync_db in reversed(cls.get_alpm_handle().get_syncdbs()):
            if not db_name or db_name == sync_db.name:
                for pkg in sync_db.search(search_query):
                    if (
                            (
                                not names_only or search_query in pkg.name
                            ) and (
                                not exact_match or search_query in ([pkg.name, ] + pkg.groups)
                            )
                    ):
                        result.append(pkg)
        return result

    @classmethod
    def find_one_repo(cls, pkg_name) -> pyalpm.Package:
        pkgs = cls.search_repo(search_query=pkg_name, exact_match=True)
        if not pkgs:
            raise PackagesNotFoundInRepo(packages=[pkg_name])
        return pkgs[0]

    @classmethod
    def get_repo_dict(cls, quiet=False) -> Dict[str, pyalpm.Package]:
        if not cls._packages_dict_cache.get(PackageSource.REPO):
            if not quiet:
                print_status_message(_("Reading repository package databases..."))
            repo_dict = {}
            for pkg in cls.search_repo(search_query=''):
                repo_dict[get_pkg_id(pkg)] = pkg
            cls._packages_dict_cache[PackageSource.REPO] = repo_dict
        return cls._packages_dict_cache[PackageSource.REPO]


def find_repo_packages(package_names: Iterable[str]) -> Tuple[List[pyalpm.Package], List[str]]:
    pacman_packages = []
    not_found_packages = []
    for package_name in package_names:
        search_results = PackageDB.search_repo(
            search_query=package_name, exact_match=True
        )
        if search_results:
            for search_result in search_results:
                pacman_packages.append(search_result)
        else:
            not_found_packages.append(package_name)
    return pacman_packages, not_found_packages


def find_local_packages(package_names: Iterable[str]) -> Tuple[List[pyalpm.Package], List[str]]:
    all_local_pkgs = PackageDB.get_local_dict()
    pacman_packages = []
    not_found_packages = []
    for package_name in package_names:
        if all_local_pkgs.get(package_name):
            pacman_packages.append(all_local_pkgs[package_name])
        else:
            not_found_packages.append(package_name)
    return pacman_packages, not_found_packages


def find_packages_not_from_repo() -> List[str]:
    local_pkg_names = PackageDB.get_local_pkgnames()
    repo_pkg_names = PackageDB.get_repo_pkgnames()
    not_found_packages = []
    for pkg_name in local_pkg_names:
        if pkg_name not in repo_pkg_names:
            not_found_packages.append(pkg_name)
    return not_found_packages
