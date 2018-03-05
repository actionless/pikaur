from pycman.config import PacmanConfig as PycmanConfig

from .core import (
    DataType, CmdTaskWorker,
)
from .version import get_package_name_and_version_matcher_from_depend_line
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

    def __init__(self, args):
        super().__init__(
            [
                "pacman",
            ] + args
        )


class PacmanColorTaskWorker(PacmanTaskWorker):

    def __init__(self, args):
        super().__init__(
            [
                "--color=always",
            ] + args
        )


class ProvidedDependency(DataType):
    name = None
    package = None
    version_matcher = None


class PackageDBCommon():

    _packages_list_cache = {}
    _packages_dict_cache = {}
    _provided_list_cache = {}
    _provided_dict_cache = {}

    repo = 'repo'
    local = 'local'

    @classmethod
    def get_repo_list(cls, **kwargs):
        if not cls._packages_list_cache.get(cls.repo):
            cls._packages_list_cache[cls.repo] = list(
                cls.get_repo_dict(**kwargs).values()
            )
        return cls._packages_list_cache[cls.repo]

    @classmethod
    def get_local_list(cls, **kwargs):
        if not cls._packages_list_cache.get(cls.local):
            cls._packages_list_cache[cls.local] = list(
                cls.get_local_dict(**kwargs).values()
            )
        return cls._packages_list_cache[cls.local]

    @classmethod
    def get_repo_dict(cls, **kwargs):
        if not cls._packages_dict_cache.get(cls.repo):
            cls._packages_dict_cache[cls.repo] = {
                pkg.name: pkg
                for pkg in cls.get_repo_list(**kwargs)
            }
        return cls._packages_dict_cache[cls.repo]

    @classmethod
    def get_local_dict(cls, **kwargs):
        if not cls._packages_dict_cache.get(cls.local):
            cls._packages_dict_cache[cls.local] = {
                pkg.name: pkg
                for pkg in cls.get_local_list(**kwargs)
            }
        return cls._packages_dict_cache[cls.local]

    @classmethod
    def _get_provided(cls, local):
        if not cls._provided_list_cache.get(local):
            cls._provided_list_cache[local] = [
                provided_pkg.name
                for provided_pkgs in cls._get_provided_dict(local).values()
                for provided_pkg in provided_pkgs
            ]
        return cls._provided_list_cache[local]

    @classmethod
    def get_repo_provided(cls):
        return cls._get_provided(cls.repo)

    @classmethod
    def get_local_provided(cls):
        return cls._get_provided(cls.local)

    @classmethod
    def _get_provided_dict(cls, local):
        if not cls._provided_dict_cache.get(local):
            provided_pkg_names = {}
            for pkg in (
                    cls.get_local_list() if local == cls.local
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
            cls._provided_dict_cache[local] = provided_pkg_names
        return cls._provided_dict_cache[local]

    @classmethod
    def get_repo_provided_dict(cls):
        return cls._get_provided_dict(cls.repo)

    @classmethod
    def get_local_provided_dict(cls):
        return cls._get_provided_dict(cls.local)


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
        if not cls._packages_list_cache.get(cls.local):
            if not kwargs.get('quiet'):
                print_status_message("Reading local package database...")
            cls._packages_list_cache[cls.local] = cls.search_local('')
        return cls._packages_list_cache[cls.local]

    @classmethod
    def search_repo_dict(cls, search_query, db_name=None):
        if '/' in search_query:
            db_name, search_query = search_query.split('/')
        result = {}
        for sync_db in reversed(cls.get_alpm_handle().get_syncdbs()):
            if not db_name or db_name == sync_db.name:
                for pkg in sync_db.search(search_query):
                    result[pkg.name] = pkg
        return result

    @classmethod
    def search_repo(cls, search_query, db_name=None):
        return list(
            cls.search_repo_dict(search_query, db_name=db_name).values()
        )

    @classmethod
    def get_repo_dict(cls, **kwargs):
        if not cls._packages_dict_cache.get(cls.repo):
            if not kwargs.get('quiet'):
                print_status_message("Reading repository package databases...")
            cls._packages_dict_cache[cls.repo] = cls.search_repo_dict('')
        return cls._packages_dict_cache[cls.repo]


def find_repo_packages(package_names, name_only=False):
    pacman_packages = []
    not_found_packages = []
    for package_name in package_names:
        search_results = PackageDB.search_repo(package_name)
        if search_results:
            pkg = search_results[0]
            if not name_only or pkg.name == package_name:
                pacman_packages.append(pkg)
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
    _repo_packages, not_found_packages = find_repo_packages(
        PackageDB.get_local_dict().keys()
    )
    return not_found_packages
