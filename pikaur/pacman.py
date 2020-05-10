""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import re
from threading import Lock
from typing import (
    List, Dict, Optional, Union, Pattern, TYPE_CHECKING
)

from pycman.config import PacmanConfig as PycmanConfig
import pyalpm

from .i18n import _
from .pacman_i18n import _p
from .core import DataType, PackageSource
from .version import VersionMatcher
from .pprint import print_stderr, color_enabled, color_line
from .args import parse_args, reconstruct_args, PACMAN_STR_OPTS, PACMAN_APPEND_OPTS
from .config import PikaurConfig
from .exceptions import PackagesNotFoundInRepo, DependencyError
from .core import sudo, spawn
from .prompt import retry_interactive_command_or_exit, retry_interactive_command


if TYPE_CHECKING:
    # pylint: disable=unused-import,cyclic-import
    from .aur import AURPackageInfo  # noqa


OFFICIAL_REPOS = (
    'core',
    'extra',
    'community',
    'multilib',
    'testing',
    'community-testing',
    'multilib-testing',
)


def create_pacman_pattern(pacman_message: str) -> Pattern[str]:
    return re.compile(
        _p(pacman_message).replace(
            "(", r"\("
        ).replace(
            ")", r"\)"
        ).replace(
            "%d", "(.*)"
        ).replace(
            "%s", "(.*)"
        ).replace(
            "%zu", "(.*)"
        ).strip()
    )


PATTERN_NOTFOUND = create_pacman_pattern("target not found: %s\n")
PATTERN_DB_NOTFOUND = create_pacman_pattern("database not found: %s\n")


def get_pacman_command(ignore_args: Optional[List[str]] = None) -> List[str]:
    ignore_args = ignore_args or []
    args = parse_args()
    pacman_path = PikaurConfig().misc.PacmanPath.get_str()
    pacman_cmd = [pacman_path, ]
    if color_enabled():
        pacman_cmd += ['--color=always']
    else:
        pacman_cmd += ['--color=never']

    for _short, arg, _default in PACMAN_STR_OPTS:
        if arg in ['color', ]:  # we force it anyway
            continue
        if arg in ignore_args:
            continue
        value = getattr(args, arg)
        if value:
            pacman_cmd += ['--' + arg, value]

    for _short, arg, _default in PACMAN_APPEND_OPTS:
        if arg in ['ignore', ]:  # we reprocess it anyway
            continue
        if arg in ignore_args:
            continue
        for value in getattr(args, arg) or []:
            pacman_cmd += ['--' + arg, value]

    return pacman_cmd


class PacmanPrint(DataType):

    full_name: str
    repo: str
    name: str


class PacmanConfig(PycmanConfig):

    def __init__(self) -> None:
        super().__init__(conf='/etc/pacman.conf')


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


DB_LOCK_REPO = Lock()
DB_LOCK_LOCAL = Lock()


class DbLockRepo():

    def __enter__(self) -> None:
        DB_LOCK_REPO.acquire()

    def __exit__(self, *_exc_details) -> None:
        DB_LOCK_REPO.release()


class DbLockLocal():

    def __enter__(self) -> None:
        DB_LOCK_LOCAL.acquire()

    def __exit__(self, *_exc_details) -> None:
        DB_LOCK_LOCAL.release()


def get_db_lock(package_source: PackageSource):
    return DbLockRepo if package_source is PackageSource.REPO else DbLockLocal


class PackageDBCommon():

    _packages_list_cache: Dict[PackageSource, List[pyalpm.Package]] = {}
    _packages_dict_cache: Dict[PackageSource, Dict[str, pyalpm.Package]] = {}
    _provided_list_cache: Dict[PackageSource, List[str]] = {}
    _provided_dict_cache: Dict[PackageSource, Dict[str, List[ProvidedDependency]]] = {}

    @classmethod
    def _discard_cache(
            cls, package_source: PackageSource
    ) -> None:
        with get_db_lock(package_source)():
            if cls._packages_list_cache.get(package_source):
                del cls._packages_list_cache[package_source]
            if cls._packages_dict_cache.get(package_source):
                del cls._packages_dict_cache[package_source]
            if cls._provided_list_cache.get(package_source):
                del cls._provided_list_cache[package_source]
            if cls._provided_dict_cache.get(package_source):
                del cls._provided_dict_cache[package_source]

    @classmethod
    def discard_local_cache(cls) -> None:
        cls._discard_cache(PackageSource.LOCAL)

    @classmethod
    def discard_repo_cache(cls) -> None:
        cls._discard_cache(PackageSource.REPO)

    @classmethod
    def get_repo_list(cls, quiet=False) -> List[pyalpm.Package]:
        pass
        # if not cls._packages_list_cache.get(PackageSource.REPO):
            # cls._packages_list_cache[PackageSource.REPO] = list(
                # cls.get_repo_dict(quiet=quiet).values()
            # )
        # return cls._packages_list_cache[PackageSource.REPO]

    @classmethod
    def get_local_list(cls, quiet=False) -> List[pyalpm.Package]:
        pass
        # if not cls._packages_list_cache.get(PackageSource.LOCAL):
            # cls._packages_list_cache[PackageSource.LOCAL] = list(
                # cls.get_local_dict(quiet=quiet).values()
            # )
        # return cls._packages_list_cache[PackageSource.LOCAL]

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
                provided_pkg_names.setdefault(pkg.name, []).append(
                    ProvidedDependency(
                        name=pkg.name,
                        package=pkg,
                        version_matcher=VersionMatcher(pkg.name)
                    )
                )
                if pkg.provides:
                    for provided_pkg_line in pkg.provides:
                        version_matcher = VersionMatcher(provided_pkg_line)
                        provided_name = version_matcher.pkg_name
                        provided_pkg_names.setdefault(provided_name, []).append(
                            ProvidedDependency(
                                name=provided_name,
                                package=pkg,
                                version_matcher=version_matcher
                            )
                        )
            for what_provides, provided_pkgs in list(provided_pkg_names.items()):
                if len(provided_pkgs) == 1 and provided_pkgs[0].name == what_provides:
                    del provided_pkg_names[what_provides]
            cls._provided_dict_cache[package_source] = provided_pkg_names
        return cls._provided_dict_cache[package_source]

    @classmethod
    def get_repo_provided_dict(cls) -> Dict[str, List[ProvidedDependency]]:
        return cls._get_provided_dict(PackageSource.REPO)

    @classmethod
    def get_local_provided_dict(cls) -> Dict[str, List[ProvidedDependency]]:
        return cls._get_provided_dict(PackageSource.LOCAL)

    @classmethod
    def get_repo_pkgnames(cls) -> List[str]:
        return [pkg.name for pkg in cls.get_repo_list()]

    @classmethod
    def get_local_pkgnames(cls) -> List[str]:
        return [pkg.name for pkg in cls.get_local_list()]


class RepositoryNotFound(Exception):
    pass


class PackageDB(PackageDBCommon):

    _alpm_handle: Optional[pyalpm.Handle] = None

    _pacman_find_cache: Dict[str, List[PacmanPrint]] = {}
    _pacman_test_cache: Dict[str, List[VersionMatcher]] = {}
    _pacman_repo_pkg_present_cache: Dict[str, bool] = {}

    @classmethod
    def get_alpm_handle(cls) -> pyalpm.Handle:
        if not cls._alpm_handle:
            cls._alpm_handle = PacmanConfig().initialize_alpm()
        if not cls._alpm_handle:
            raise Exception("Cannot initialize ALPM")
        return cls._alpm_handle

    @classmethod
    def discard_local_cache(cls) -> None:
        super().discard_local_cache()
        cls._alpm_handle = None
        cls._pacman_test_cache = {}

    @classmethod
    def discard_repo_cache(cls) -> None:
        super().discard_repo_cache()
        cls._alpm_handle = None
        cls._pacman_find_cache = {}
        cls._pacman_repo_pkg_present_cache = {}

    @classmethod
    def search_local(cls, search_query: str) -> List[pyalpm.Package]:
        return cls.get_alpm_handle().get_localdb().search(search_query)

    @classmethod
    def get_local_list(cls, quiet=False) -> List[pyalpm.Package]:
        if not cls._packages_list_cache.get(PackageSource.LOCAL):
            with DbLockLocal():
                if not quiet:
                    print_stderr(_("Reading local package database..."))
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
    def _get_provided_dict(
            cls, package_source: PackageSource
    ) -> Dict[str, List[ProvidedDependency]]:

        if not cls._provided_dict_cache.get(package_source):
            provided_pkg_names = super()._get_provided_dict(package_source)
            if package_source == PackageSource.REPO:
                for _what_provides, provided_pkgs in provided_pkg_names.items():
                    provided_pkgs.sort(key=lambda p: "{}{}".format(
                        cls.get_repo_priority(p.package.db.name),
                        p.package.name
                    ))
            cls._provided_dict_cache[package_source] = provided_pkg_names
        return cls._provided_dict_cache[package_source]

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
        return list(reversed(result))

    @classmethod
    def get_repo_list(cls, quiet=False) -> List[pyalpm.Package]:
        if not cls._packages_list_cache.get(PackageSource.REPO):
            with DbLockRepo():
                if not quiet:
                    print_stderr(_("Reading repository package databases..."))
                cls._packages_list_cache[PackageSource.REPO] = cls.search_repo(
                    search_query=''
                )
        return cls._packages_list_cache[PackageSource.REPO]

    @classmethod
    def get_last_installed_package_date(cls) -> int:
        repo_names = []
        for repo in PackageDB.get_repo_list():
            repo_names.append(repo.name)
        packages = []
        for package in PackageDB.get_local_list():
            if package.name in repo_names:
                packages.append(package)
        packages_by_date = sorted(packages, key=lambda x: -x.installdate)
        return int(packages_by_date[0].installdate)

    @classmethod
    def get_print_format_output(cls, cmd_args: List[str]) -> List[PacmanPrint]:
        cache_index = ' '.join(sorted(cmd_args))
        cached_pkg = cls._pacman_find_cache.get(cache_index)
        if cached_pkg is not None:
            return cached_pkg
        results: List[PacmanPrint] = []
        found_packages_output = spawn(
            cmd_args + ['--print-format', '%r/%n']
        ).stdout_text
        if found_packages_output:
            for line in found_packages_output.splitlines():
                try:
                    repo_name, pkg_name = line.split('/')
                except ValueError:
                    print_stderr(line)
                    continue
                else:
                    results.append(PacmanPrint(
                        full_name=line,
                        repo=repo_name,
                        name=pkg_name
                    ))
        cls._pacman_find_cache[cache_index] = results
        return results

    @classmethod
    def get_pacman_test_output(cls, cmd_args: List[str]) -> List[VersionMatcher]:
        if not cmd_args:
            return []
        cache_index = ' '.join(sorted(cmd_args))
        cached_pkg = cls._pacman_test_cache.get(cache_index)
        if cached_pkg is not None:
            return cached_pkg
        results: List[VersionMatcher] = []
        not_found_packages_output = spawn(
            # pacman --deptest flag conflicts with some --sync options:
            get_pacman_command(ignore_args=[
                'overwrite'
            ]) + ['--deptest', ] + cmd_args
        ).stdout_text
        if not not_found_packages_output:
            cls._pacman_test_cache[cache_index] = results
            return results
        for line in not_found_packages_output.splitlines():
            try:
                version_matcher = VersionMatcher(line)
            except ValueError:
                print_stderr(line)
                continue
            else:
                results.append(version_matcher)
        return results

    @classmethod
    def get_not_found_repo_packages(cls, pkg_lines: List[str]) -> List[str]:
        not_found_pkg_names = []
        pkg_names_to_check: List[str] = []
        for pkg_name in pkg_lines:
            if pkg_name in cls._pacman_repo_pkg_present_cache:
                if not cls._pacman_repo_pkg_present_cache[pkg_name]:
                    not_found_pkg_names.append(pkg_name)
            else:
                pkg_names_to_check += pkg_name.split(',')

        if not pkg_names_to_check:
            return not_found_pkg_names

        results = spawn(
            get_pacman_command() + ['--sync', '--print-format=%%'] + pkg_names_to_check
        ).stderr_text.splitlines()
        new_not_found_pkg_names = []
        for result in results:
            for pattern in (PATTERN_NOTFOUND, PATTERN_DB_NOTFOUND, ):
                groups = pattern.findall(result)
                if groups:
                    pkg_name = VersionMatcher(groups[0]).pkg_name
                    new_not_found_pkg_names.append(pkg_name)

        for pkg_name in pkg_names_to_check:
            cls._pacman_repo_pkg_present_cache[pkg_name] = pkg_name not in new_not_found_pkg_names

        return not_found_pkg_names + new_not_found_pkg_names

    @classmethod
    def get_not_found_local_packages(cls, pkg_lines: List[str]) -> List[str]:
        not_found_version_matchers = cls.get_pacman_test_output([
            splitted_pkg_name for splitted_pkg_names in
            [pkg_name.split(',') for pkg_name in pkg_lines]
            for splitted_pkg_name in splitted_pkg_names
        ])
        not_found_packages = list(set(
            vm.pkg_name for vm in not_found_version_matchers
        ))
        return not_found_packages

    @classmethod
    def find_repo_package(cls, pkg_name: str) -> pyalpm.Package:
        # @TODO: interactively ask for multiple providers and save the answer?
        if cls._pacman_repo_pkg_present_cache.get(pkg_name) is False:
            raise PackagesNotFoundInRepo(packages=[pkg_name])
        all_repo_pkgs = PackageDB.get_repo_dict()
        results = cls.get_print_format_output(
            get_pacman_command() + ['--sync'] + pkg_name.split(',')
        )
        if not results:
            raise PackagesNotFoundInRepo(packages=[pkg_name])
        found_pkgs = [all_repo_pkgs[result.full_name] for result in results]
        if len(results) == 1:
            return found_pkgs[0]

        pkg_name = VersionMatcher(pkg_name).pkg_name
        for pkg in found_pkgs:
            if pkg.name == pkg_name:
                return pkg
        for pkg in found_pkgs:
            if pkg.provides:
                for provided_pkg_line in pkg.provides:
                    provided_name = VersionMatcher(provided_pkg_line).pkg_name
                    if provided_name == pkg_name:
                        return pkg
        raise PackagesNotFoundInRepo(packages=[pkg_name])


def get_upgradeable_package_names() -> List[str]:
    upgradeable_packages_output = spawn(
        get_pacman_command() + ['--query', '--upgrades', '--quiet']
    ).stdout_text
    if not upgradeable_packages_output:
        return []
    return upgradeable_packages_output.splitlines()


def find_upgradeable_packages() -> List[pyalpm.Package]:
    all_repo_pkgs = PackageDB.get_repo_dict()

    pkg_names = get_upgradeable_package_names()
    if not pkg_names:
        return []

    all_local_pkgs = PackageDB.get_local_dict()
    results = PackageDB.get_print_format_output(
        get_pacman_command() + ['--sync'] + pkg_names
    )
    return [
        all_repo_pkgs[result.full_name] for result in results
        if result.name in all_local_pkgs
    ]


def find_sysupgrade_packages(ignore_pkgs: Optional[List[str]] = None) -> List[pyalpm.Package]:
    all_repo_pkgs = PackageDB.get_repo_dict()

    extra_args: List[str] = []
    for excluded_pkg_name in ignore_pkgs or []:
        extra_args.append('--ignore')
        # pacman's --ignore doesn't work with repo name:
        extra_args.append(strip_repo_name(excluded_pkg_name))

    results = PackageDB.get_print_format_output(
        get_pacman_command() + ['--sync'] +
        ['--sysupgrade'] * parse_args().sysupgrade +
        extra_args
    )
    return [
        all_repo_pkgs[result.full_name] for result in results
    ]


def find_packages_not_from_repo() -> List[str]:
    local_pkg_names = PackageDB.get_local_pkgnames()
    repo_pkg_names = PackageDB.get_repo_pkgnames()
    not_found_packages = []
    for pkg_name in local_pkg_names:
        if pkg_name not in repo_pkg_names:
            not_found_packages.append(pkg_name)
    return not_found_packages


def refresh_pkg_db() -> None:
    args = parse_args()
    if args.refresh:
        pacman_args = (sudo(
            get_pacman_command() + ['--sync'] + ['--refresh'] * args.refresh
        ))
        retry_interactive_command_or_exit(pacman_args)


def install_built_deps(
        deps_names_and_paths: Dict[str, str],
        resolved_conflicts: Optional[List[List[str]]] = None
) -> None:
    if not deps_names_and_paths:
        return

    local_packages = PackageDB.get_local_dict()
    args = parse_args()

    def _get_pacman_command() -> List[str]:
        return get_pacman_command() + reconstruct_args(args, ignore_args=[
            'upgrade',
            'asdeps',
            'sync',
            'sysupgrade',
            'refresh',
            'ignore',
            'downloadonly',
        ])

    explicitly_installed_deps = []
    for pkg_name, _path in deps_names_and_paths.items():
        print(color_line(pkg_name, 14))
        if pkg_name in local_packages and local_packages[pkg_name].reason == 0:
            explicitly_installed_deps.append(pkg_name)
    deps_upgrade_success = True
    if len(explicitly_installed_deps) < len(deps_names_and_paths):
        deps_upgrade_success = retry_interactive_command(
            sudo(
                _get_pacman_command() + [
                    '--upgrade',
                    '--asdeps',
                ] + [
                    path for name, path in deps_names_and_paths.items()
                    if name not in explicitly_installed_deps
                ],
            ),
            pikspect=True,
            conflicts=resolved_conflicts,
        )

    explicit_upgrade_success = True
    if explicitly_installed_deps:
        explicit_upgrade_success = retry_interactive_command(
            sudo(
                _get_pacman_command() + [
                    '--upgrade',
                ] + [
                    path for name, path in deps_names_and_paths.items()
                    if name in explicitly_installed_deps
                ]
            ),
            pikspect=True,
            conflicts=resolved_conflicts,
        )

    PackageDB.discard_local_cache()

    if not (deps_upgrade_success and explicit_upgrade_success):
        raise DependencyError()


def strip_repo_name(pkg_name: str) -> str:
    return pkg_name.split('/', 1)[-1]
