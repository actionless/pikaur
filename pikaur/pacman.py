from pycman.config import PacmanConfig as PycmanConfig

from .core import (
    DataType, CmdTaskWorker,
)
from .version import get_package_name_and_version_matcher_from_depend_line


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
    version_matcher = None


class PackageDBCommon():

    _packages_list_cache = {}
    _packages_dict_cache = {}
    _provided_list_cache = {}
    _provided_dict_cache = {}

    repo = 'repo'
    local = 'local'

    @classmethod
    def get_repo_list(cls):
        if not cls._packages_list_cache.get(cls.repo):
            cls._packages_list_cache[cls.repo] = cls.get_repo_dict().values()
        return cls._packages_list_cache[cls.repo]

    @classmethod
    def get_local_list(cls):
        if not cls._packages_list_cache.get(cls.local):
            cls._packages_list_cache[cls.local] = cls.get_local_dict().values()
        return cls._packages_list_cache[cls.local]

    @classmethod
    def get_repo_dict(cls):
        if not cls._packages_dict_cache.get(cls.repo):
            cls._packages_dict_cache[cls.repo] = {
                pkg.name: pkg
                for pkg in cls.get_repo_list()
            }
        return cls._packages_dict_cache[cls.repo]

    @classmethod
    def get_local_dict(cls):
        if not cls._packages_dict_cache.get(cls.local):
            cls._packages_dict_cache[cls.local] = {
                pkg.name: pkg
                for pkg in cls.get_local_list()
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
                                name=provided_name, version_matcher=version_matcher
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
    def get_local_list(cls):
        if not cls._packages_list_cache.get(cls.local):
            print("Reading local package database...")
            cls._packages_list_cache[cls.local] = cls.get_alpm_handle().get_localdb().search('')
        return cls._packages_list_cache[cls.local]

    @classmethod
    def get_repo_list(cls):
        if not cls._packages_list_cache.get(cls.repo):
            print("Reading repository package databases...")
            result = []
            for sync_db in cls.get_alpm_handle().get_syncdbs():
                result += sync_db.search('')
            cls._packages_list_cache[cls.repo] = result
        return cls._packages_list_cache[cls.repo]


def find_pacman_packages(packages, local=False):
    all_repo_packages = (
        PackageDB.get_local_dict() if local else PackageDB.get_repo_dict()
    ).keys()
    pacman_packages = []
    not_found_packages = []
    for package_name in packages:
        if package_name in all_repo_packages:
            pacman_packages.append(package_name)
        else:
            not_found_packages.append(package_name)
    return pacman_packages, not_found_packages


def find_repo_packages(packages):
    return find_pacman_packages(packages, local=False)


def find_local_packages(packages):
    return find_pacman_packages(packages, local=True)


def find_packages_not_from_repo():
    _repo_packages, not_found_packages = find_repo_packages(
        PackageDB.get_local_dict().keys()
    )
    return {
        pkg_name: PackageDB.get_local_dict()[pkg_name].version
        for pkg_name in not_found_packages
    }
