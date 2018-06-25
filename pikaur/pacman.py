import gettext
import re
from typing import List, Dict, Tuple, Iterable, Optional, Union, TYPE_CHECKING

from pycman.config import PacmanConfig as PycmanConfig
import pyalpm

from .i18n import _
from .core import DataType, PackageSource
from .version import VersionMatcher
from .pprint import print_stderr, color_enabled, bold_line
from .args import PikaurArgs
from .config import PikaurConfig
from .exceptions import PackagesNotFoundInRepo
from .core import sudo, spawn
from .prompt import retry_interactive_command_or_exit

if TYPE_CHECKING:
    # pylint: disable=unused-import
    from .aur import AURPackageInfo  # noqa


PACMAN_TRANSLATION = gettext.translation('pacman', fallback=True)


def _p(msg: str) -> str:
    return PACMAN_TRANSLATION.gettext(msg)


OFFICIAL_REPOS = (
    'testing',
    'core',
    'extra',
    'community-testing',
    'community',
    'multilib-testing',
    'multilib',
)


ANSWER_Y = _p("Y")
ANSWER_N = _p("N")
QUESTION_YN_YES = _p("[Y/n]")
QUESTION_YN_NO = _p("[y/N]")


def format_pacman_question(message: str, question=QUESTION_YN_YES) -> str:
    return bold_line(" {} {} ".format(_p(message), question))


MESSAGE_PACKAGES = _p('Packages')

QUESTION_PROCEED = format_pacman_question('Proceed with installation?')
QUESTION_REMOVE = format_pacman_question('Do you want to remove these packages?')
QUESTION_CONFLICT = format_pacman_question(
    '%s and %s are in conflict. Remove %s?', QUESTION_YN_NO
)
QUESTION_CONFLICT_VIA_PROVIDED = format_pacman_question(
    '%s and %s are in conflict (%s). Remove %s?', QUESTION_YN_NO
)


def format_conflicts(conflicts: List[List[str]]) -> List[str]:
    return [
        QUESTION_CONFLICT % (new_pkg, old_pkg, old_pkg)
        for new_pkg, old_pkg in conflicts
    ] + [
        (
            re.escape(QUESTION_CONFLICT_VIA_PROVIDED % (new_pkg, old_pkg, '.*', old_pkg))
        ).replace(r"\.\*", ".*")
        for new_pkg, old_pkg in conflicts
    ]


def get_pacman_command() -> List[str]:
    pacman_path = PikaurConfig().misc.PacmanPath
    if color_enabled():
        return [pacman_path, '--color=always']
    return [pacman_path, '--color=never']


class PacmanPrint(DataType):

    full_name: str
    repo: str
    name: str


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
    def _discard_cache(
            cls, package_source: PackageSource
    ) -> None:
        if cls._packages_list_cache.get(package_source):
            del cls._packages_list_cache[package_source]
        if cls._packages_dict_cache.get(package_source):
            del cls._packages_dict_cache[package_source]

    @classmethod
    def discard_local_cache(cls) -> None:
        cls._discard_cache(PackageSource.LOCAL)

    @classmethod
    def discard_repo_cache(cls) -> None:
        cls._discard_cache(PackageSource.REPO)

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
                if len(provided_pkgs) == 1 and provided_pkgs[0] == what_provides:
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
    def get_repo_pkgnames(cls):
        return [pkg.name for pkg in cls.get_repo_list()]

    @classmethod
    def get_local_pkgnames(cls):
        return [pkg.name for pkg in cls.get_local_list()]


class RepositoryNotFound(Exception):
    pass


class PackageDB(PackageDBCommon):

    _alpm_handle: Optional[pyalpm.Handle] = None

    _pacman_find_cache: Dict[str, pyalpm.Package] = {}

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
    def discard_repo_cache(cls) -> None:
        super().discard_repo_cache()
        cls._alpm_handle = None
        cls._pacman_find_cache = {}

    @classmethod
    def search_local(cls, search_query: str) -> List[pyalpm.Package]:
        return cls.get_alpm_handle().get_localdb().search(search_query)

    @classmethod
    def get_local_list(cls, quiet=False) -> List[pyalpm.Package]:
        if not cls._packages_list_cache.get(PackageSource.LOCAL):
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
        cache_index = ' '.join(cmd_args)
        cached_pkg = cls._pacman_find_cache.get(cache_index)
        if cached_pkg is not None:
            return cached_pkg
        results: List[PacmanPrint] = []
        found_packages_output = spawn(
            cmd_args + ['--print-format', '%r/%n']
        ).stdout_text
        if not found_packages_output:
            cls._pacman_find_cache[cache_index] = results
            return results
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
    def find_repo_package(cls, pkg_name: str) -> pyalpm.Package:
        # @TODO: interactively ask for multiple providers and save the answer?
        all_repo_pkgs = PackageDB.get_repo_dict()
        results = cls.get_print_format_output(
            get_pacman_command() + ['--sync'] + [pkg_name]
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
        raise Exception(f'Failed to find "{pkg_name}" in the output: {found_pkgs}')


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


def find_sysupgrade_packages() -> List[pyalpm.Package]:
    all_repo_pkgs = PackageDB.get_repo_dict()

    results = PackageDB.get_print_format_output(
        get_pacman_command() + ['--sync', '--sysupgrade']
    )
    return [
        all_repo_pkgs[result.full_name] for result in results
    ]


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


def refresh_pkg_db(args: PikaurArgs) -> None:
    if args.refresh:
        pacman_args = (sudo(
            get_pacman_command() + ['--sync'] + ['--refresh'] * args.refresh
        ))
        retry_interactive_command_or_exit(
            pacman_args, args=args
        )
