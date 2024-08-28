"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import fnmatch
import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

import pyalpm

from .alpm import PyAlpmWrapper
from .args import PACMAN_APPEND_OPTS, get_pacman_str_opts, parse_args, reconstruct_args
from .config import PikaurConfig
from .exceptions import DependencyError, PackagesNotFoundInRepoError
from .i18n import translate
from .lock import FancyLock
from .logging_extras import create_logger
from .pacman_i18n import _p
from .pikaprint import color_enabled, print_stderr
from .pikatypes import DataType, PackageSource
from .privilege import sudo
from .prompt import retry_interactive_command, retry_interactive_command_or_exit
from .provider import Provider
from .spawn import spawn
from .version import VersionMatcher

if TYPE_CHECKING:
    # pylint: disable=cyclic-import
    from pathlib import Path
    from re import Pattern
    from typing import Final

    from .pikatypes import AURPackageInfo


REPO_NAME_DELIMITER: "Final" = "/"


logger = create_logger("pacman")


def create_pacman_pattern(pacman_message: str) -> "Pattern[str]":
    return re.compile(
        _p(pacman_message).replace(
            "(", r"\(",
        ).replace(
            ")", r"\)",
        ).replace(
            "%d", "(.*)",
        ).replace(
            "%s", "(.*)",
        ).replace(
            "%zu", "(.*)",
        ).strip(),
    )


def get_pacman_command(  # pylint: disable=too-many-branches
        ignore_args: list[str] | None = None,
) -> list[str]:
    ignore_args = ignore_args or []
    args = parse_args()
    pacman_path = PikaurConfig().misc.PacmanPath.get_str()
    pacman_cmd = [pacman_path]
    if color_enabled():
        pacman_cmd += ["--color=always"]
    else:
        pacman_cmd += ["--color=never"]

    for short, long, _default, _help in get_pacman_str_opts():
        arg = long or short
        if not arg:
            continue
        if arg == "color":  # we force it anyway
            continue
        if arg in ignore_args:
            continue
        value = getattr(args, arg)
        if value:
            if long:
                pacman_cmd += ["--" + long, value]
            elif short:
                pacman_cmd += ["-" + short, value]

    for short, long, _default, _help in PACMAN_APPEND_OPTS:
        arg = long or short
        if not arg:
            continue
        if arg == "ignore":  # we reprocess it anyway
            continue
        if arg in ignore_args:
            continue
        for value in getattr(args, arg) or []:
            if long:
                pacman_cmd += ["--" + long, value]
            elif short:
                pacman_cmd += ["-" + short, value]

    return pacman_cmd


class RawPrintFormat(DataType):

    returncode: int
    stdout_text: str
    stderr_text: str


class PacmanPrint(DataType):

    full_name: str
    repo: str
    name: str


class ProvidedDependency(DataType):
    name: str
    package: pyalpm.Package
    version_matcher: VersionMatcher

    def __repr__(self) -> str:
        return (
            f'<{self.__class__.__name__} "{self.name}" '
            f"{self.version_matcher.line}>"
        )


def get_pkg_id(pkg: "AURPackageInfo | pyalpm.Package") -> str:
    if isinstance(pkg, pyalpm.Package):
        return f"{pkg.db.name}/{pkg.name}"
    return f"aur/{pkg.name}"


class DbLockRepo(FancyLock):
    pass


class DbLockLocal(FancyLock):
    pass


def get_db_lock(package_source: PackageSource) -> type[DbLockRepo | DbLockLocal]:
    return DbLockRepo if package_source is PackageSource.REPO else DbLockLocal


class PackageDBCommon(ABC):

    _packages_list_cache: ClassVar[dict[PackageSource, list[pyalpm.Package]]] = {}
    _packages_dict_cache: ClassVar[dict[PackageSource, dict[str, pyalpm.Package]]] = {}
    _provided_list_cache: ClassVar[dict[PackageSource, list[str]]] = {}
    _provided_dict_cache: ClassVar[dict[PackageSource, dict[str, list[ProvidedDependency]]]] = {}

    @classmethod
    def _discard_cache(
            cls, package_source: PackageSource,
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
        logger.debug("Discarding local cache...")
        cls._discard_cache(PackageSource.LOCAL)

    @classmethod
    def discard_repo_cache(cls) -> None:
        logger.debug("Discarding repo cache...")
        cls._discard_cache(PackageSource.REPO)

    @classmethod
    @abstractmethod
    def get_repo_list(cls, *, quiet: bool = False) -> list[pyalpm.Package]:  # pragma: no cover
        pass
        # if not cls._packages_list_cache.get(PackageSource.REPO):
        #     cls._packages_list_cache[PackageSource.REPO] = list(
        #         cls.get_repo_dict(quiet=quiet).values()
        #     )
        # return cls._packages_list_cache[PackageSource.REPO]

    @classmethod
    @abstractmethod
    def get_local_list(cls, *, quiet: bool = False) -> list[pyalpm.Package]:  # pragma: no cover
        pass
        # if not cls._packages_list_cache.get(PackageSource.LOCAL):
        #     cls._packages_list_cache[PackageSource.LOCAL] = list(
        #         cls.get_local_dict(quiet=quiet).values()
        #     )
        # return cls._packages_list_cache[PackageSource.LOCAL]

    @classmethod
    def get_repo_dict(cls, *, quiet: bool = False) -> dict[str, pyalpm.Package]:
        if not cls._packages_dict_cache.get(PackageSource.REPO):
            cls._packages_dict_cache[PackageSource.REPO] = {
                get_pkg_id(pkg): pkg
                for pkg in cls.get_repo_list(quiet=quiet)
            }
        return cls._packages_dict_cache[PackageSource.REPO]

    @classmethod
    def get_local_dict(cls, *, quiet: bool = False) -> dict[str, pyalpm.Package]:
        if not cls._packages_dict_cache.get(PackageSource.LOCAL):
            cls._packages_dict_cache[PackageSource.LOCAL] = {
                pkg.name: pkg
                for pkg in cls.get_local_list(quiet=quiet)
            }
        return cls._packages_dict_cache[PackageSource.LOCAL]

    @classmethod
    def get_provided_dict(
            cls, package_source: PackageSource,
    ) -> dict[str, list[ProvidedDependency]]:

        if not cls._provided_dict_cache.get(package_source):
            provided_pkg_names: dict[str, list[ProvidedDependency]] = {}
            for pkg in (
                    cls.get_local_list() if package_source == PackageSource.LOCAL
                    else cls.get_repo_list()
            ):
                provided_pkg_names.setdefault(pkg.name, []).append(
                    ProvidedDependency(
                        name=pkg.name,
                        package=pkg,
                        version_matcher=VersionMatcher(pkg.name, is_pkg_deps=True),
                    ),
                )
                if pkg.provides:
                    for provided_pkg_line in pkg.provides:
                        version_matcher = VersionMatcher(provided_pkg_line, is_pkg_deps=True)
                        provided_name = version_matcher.pkg_name
                        provided_pkg_names.setdefault(provided_name, []).append(
                            ProvidedDependency(
                                name=provided_name,
                                package=pkg,
                                version_matcher=version_matcher,
                            ),
                        )
            for what_provides, provided_pkgs in list(provided_pkg_names.items()):
                if len(provided_pkgs) == 1 and provided_pkgs[0].name == what_provides:
                    del provided_pkg_names[what_provides]
            cls._provided_dict_cache[package_source] = provided_pkg_names
        return cls._provided_dict_cache[package_source]

    @classmethod
    def get_repo_provided_dict(cls) -> dict[str, list[ProvidedDependency]]:
        return cls.get_provided_dict(PackageSource.REPO)

    @classmethod
    def get_local_provided_dict(cls) -> dict[str, list[ProvidedDependency]]:
        return cls.get_provided_dict(PackageSource.LOCAL)

    @classmethod
    def get_repo_pkgnames(cls) -> list[str]:
        return [pkg.name for pkg in cls.get_repo_list()]

    @classmethod
    def get_local_pkgnames(cls) -> list[str]:
        return [pkg.name for pkg in cls.get_local_list()]


class RepositoryNotFoundError(Exception):
    pass


class PackageDB(PackageDBCommon, PyAlpmWrapper):

    _pacman_pformat_cache: ClassVar[dict[str, RawPrintFormat]] = {}
    _pacman_test_cache: ClassVar[dict[str, list[VersionMatcher]]] = {}
    _pacman_repo_pkg_present_cache: ClassVar[dict[str, bool]] = {}

    @classmethod
    def discard_local_cache(cls) -> None:
        super().discard_local_cache()
        cls._alpm_handle = None
        cls._pacman_test_cache = {}

    @classmethod
    def discard_repo_cache(cls) -> None:
        super().discard_repo_cache()
        cls._alpm_handle = None
        cls._pacman_pformat_cache = {}
        cls._pacman_repo_pkg_present_cache = {}

    @classmethod
    def search_local(cls, search_query: str) -> list[pyalpm.Package]:
        return cls.get_alpm_handle().get_localdb().search(search_query)

    @classmethod
    def get_local_list(cls, *, quiet: bool = False) -> list[pyalpm.Package]:
        if not cls._packages_list_cache.get(PackageSource.LOCAL):
            with DbLockLocal():
                if not quiet:
                    print_stderr(translate("Reading local package database..."))
                cls._packages_list_cache[PackageSource.LOCAL] = cls.search_local("")
        return cls._packages_list_cache[PackageSource.LOCAL]

    @classmethod
    def get_repo_priority(cls, repo_name: str) -> int:
        """0 is the highest priority."""
        repos = [r.name for r in cls.get_alpm_handle().get_syncdbs()]
        if repo_name not in repos:
            repo_not_found = f"'{repo_name}' in {repos}"
            raise RepositoryNotFoundError(repo_not_found)
        return repos.index(repo_name)

    @classmethod
    def get_provided_dict(
            cls, package_source: PackageSource,
    ) -> dict[str, list[ProvidedDependency]]:

        if not cls._provided_dict_cache.get(package_source):
            provided_pkg_names = super().get_provided_dict(package_source)
            if package_source == PackageSource.REPO:
                for provided_pkgs in provided_pkg_names.values():
                    provided_pkgs.sort(
                        key=lambda p: f"{cls.get_repo_priority(p.package.db.name)}{p.package.name}",
                    )
            cls._provided_dict_cache[package_source] = provided_pkg_names
        return cls._provided_dict_cache[package_source]

    @classmethod
    def search_repo(
            cls,
            search_query: str,
            db_names: list[str] | None = None,
            *,
            names_only: bool = False,
            exact_match: bool = False,
    ) -> list[pyalpm.Package]:
        if REPO_NAME_DELIMITER in search_query:
            db_name, search_query = search_query.split(REPO_NAME_DELIMITER)
            db_names = [db_name]
        return list(reversed([
            pkg
            for sync_db in reversed(cls.get_alpm_handle().get_syncdbs())
            if not db_names or (sync_db.name in db_names)
            for pkg in sync_db.search(search_query)
            if (
                (
                    not names_only or search_query in pkg.name
                ) and (
                    not exact_match or search_query in ({pkg.name, *pkg.groups})
                )
            )
        ]))

    @classmethod
    def get_repo_list(cls, *, quiet: bool = False) -> list[pyalpm.Package]:
        if not cls._packages_list_cache.get(PackageSource.REPO):
            with DbLockRepo():
                if not quiet:
                    print_stderr(translate("Reading repository package databases..."))
                cls._packages_list_cache[PackageSource.REPO] = cls.search_repo(
                    search_query="",
                )
        return cls._packages_list_cache[PackageSource.REPO]

    @classmethod
    def get_last_installed_package_date(cls) -> int:
        repo_names = [
            repo.name
            for repo in PackageDB.get_repo_list()
        ]
        packages = [
            package
            for package in PackageDB.get_local_list()
            if package.name in repo_names
        ]
        packages_by_date = sorted(packages, key=lambda x: -x.installdate)
        return int(packages_by_date[0].installdate)

    @classmethod
    def _get_print_format_output_raw(
            cls, cmd_args: list[str], *, check_deps: bool = True, package_only: bool = False,
    ) -> RawPrintFormat:
        final_args = [*cmd_args, "--print-format", "%r/%n"]
        if not check_deps and not package_only:
            final_args.append("--nodeps")
        if package_only:
            final_args += ["--nodeps", "--nodeps"]
        cache_index = " ".join(sorted(final_args))
        if cls._pacman_pformat_cache.get(cache_index) is None:
            proc = spawn(final_args)
            cls._pacman_pformat_cache[cache_index] = RawPrintFormat(
                returncode=proc.returncode,
                stdout_text=proc.stdout_text,
                stderr_text=proc.stderr_text,
            )
        else:
            logger.debug("cached pformat {}", final_args)
        return cls._pacman_pformat_cache[cache_index]

    @classmethod
    def get_print_format_output(
            cls, cmd_args: list[str], *, check_deps: bool = True, package_only: bool = False,
    ) -> list[PacmanPrint]:
        results: list[PacmanPrint] = []
        raw_result = cls._get_print_format_output_raw(
            cmd_args=cmd_args,
            check_deps=check_deps,
            package_only=package_only,
        )
        if raw_result.returncode != 0:
            raise DependencyError((raw_result.stderr_text or "") + (raw_result.stdout_text or ""))
        found_packages_output = raw_result.stdout_text
        if found_packages_output:
            for line in found_packages_output.splitlines():
                try:
                    repo_name, pkg_name = line.split(REPO_NAME_DELIMITER)
                except ValueError:
                    print_stderr(line)
                    continue
                else:
                    results.append(PacmanPrint(
                        full_name=line,
                        repo=repo_name,
                        name=pkg_name,
                    ))
        return results

    @classmethod
    def get_sync_print_format_output(
            cls, pkg_names: list[str], *, check_deps: bool = True, package_only: bool = False,
    ) -> list[PacmanPrint]:
        return cls.get_print_format_output(
            [*get_pacman_command(), "--sync", *pkg_names],
            check_deps=check_deps,
            package_only=package_only,
        )

    @classmethod
    def get_pacman_test_output(cls, cmd_args: list[str]) -> list[VersionMatcher]:
        if not cmd_args:
            return []
        cache_index = " ".join(sorted(cmd_args))
        cached_pkgs = cls._pacman_test_cache.get(cache_index)
        if cached_pkgs is not None:
            # logger.debug("cached deptest {}", cmd_args)
            return cached_pkgs
        results: list[VersionMatcher] = []
        not_found_packages_output = spawn([
            # pacman --deptest flag conflicts with some --sync options:
            *get_pacman_command(ignore_args=["overwrite"]),
            "--deptest",
            *cmd_args,
        ]).stdout_text
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
        cls._pacman_test_cache[cache_index] = results
        return results

    @classmethod
    def get_not_found_repo_packages(cls, pkg_lines: list[str]) -> list[str]:

        pattern_notfound = create_pacman_pattern("target not found: %s\n")
        pattern_db_notfound = create_pacman_pattern("database not found: %s\n")

        not_found_pkg_names = []
        pkg_names_to_check: list[str] = []
        for pkg_name in pkg_lines:
            if pkg_name not in cls._pacman_repo_pkg_present_cache:
                pkg_names_to_check += pkg_name.split(",")
            elif not cls._pacman_repo_pkg_present_cache[pkg_name]:
                not_found_pkg_names.append(VersionMatcher(pkg_name).pkg_name)

        logger.debug(
            "get_not_found_repo_packages: pkg_names_to_check={} not_found_pkg_names={}",
            pkg_names_to_check, not_found_pkg_names,
        )
        if not pkg_names_to_check:
            return not_found_pkg_names

        results = (cls._get_print_format_output_raw(
            cmd_args=[*get_pacman_command(), "--sync", *pkg_names_to_check],
            check_deps=False,
            package_only=False,
        ).stderr_text or "").splitlines()
        new_not_found_pkg_names = []
        for result in results:
            for pattern in (pattern_notfound, pattern_db_notfound):
                groups = pattern.findall(result)
                if groups:
                    pkg_name = VersionMatcher(groups[0]).pkg_name
                    new_not_found_pkg_names.append(pkg_name)

        end_result = not_found_pkg_names + new_not_found_pkg_names
        for pkg_name in pkg_names_to_check:
            cls._pacman_repo_pkg_present_cache[pkg_name] = (
                VersionMatcher(pkg_name).pkg_name not in end_result
            )

        return end_result

    @classmethod
    def get_not_found_local_packages(cls, pkg_lines: list[str]) -> list[str]:
        not_found_version_matchers = cls.get_pacman_test_output([
            splitted_pkg_name for splitted_pkg_names in
            [pkg_name.split(",") for pkg_name in pkg_lines]
            for splitted_pkg_name in splitted_pkg_names
        ])
        return list({
            vm.pkg_name for vm in not_found_version_matchers
        })

    @classmethod
    def find_repo_package(cls, pkg_name: str) -> pyalpm.Package:

        if cls._pacman_repo_pkg_present_cache.get(pkg_name) is False:
            raise PackagesNotFoundInRepoError(packages=[pkg_name])
        all_repo_pkgs = PackageDB.get_repo_dict()
        try:
            results = cls.get_sync_print_format_output(
                pkg_names=pkg_name.split(","),
                package_only=True,
            )
        except DependencyError as exc:
            raise PackagesNotFoundInRepoError(packages=[pkg_name]) from exc
        found_pkgs = [all_repo_pkgs[result.full_name] for result in results]
        if len(results) == 1:
            return found_pkgs[0]

        pkg_name = VersionMatcher(pkg_name).pkg_name
        matching_pkgs: list[pyalpm.Package] = [
            pkg
            for pkg in found_pkgs
            if pkg.name == pkg_name
        ]
        for pkg in found_pkgs:
            if pkg.provides:
                for provided_pkg_line in pkg.provides:
                    provided_name = VersionMatcher(provided_pkg_line).pkg_name
                    if provided_name == pkg_name:
                        matching_pkgs.append(pkg)
        if not matching_pkgs:
            raise PackagesNotFoundInRepoError(packages=[pkg_name])
        return Provider.choose(
            dependency=pkg_name, options=matching_pkgs,
        )

    @classmethod
    def get_local_pkg_uncached(cls, name: str) -> pyalpm.Package:
        return cls.get_alpm_handle().get_localdb().get_pkg(name)


def get_upgradeable_package_names() -> list[str]:
    upgradeable_packages_output = spawn([
        *get_pacman_command(), "--query", "--upgrades", "--quiet",
    ]).stdout_text
    if not upgradeable_packages_output:
        return []
    return upgradeable_packages_output.splitlines()


def find_upgradeable_packages() -> list[pyalpm.Package]:
    all_repo_pkgs = PackageDB.get_repo_dict()

    pkg_names = get_upgradeable_package_names()
    if not pkg_names:
        return []

    all_local_pkgs = PackageDB.get_local_dict()
    results: list[PacmanPrint] = []
    try:
        results = PackageDB.get_sync_print_format_output(pkg_names=pkg_names)
    except DependencyError as exc:
        logger.debug(translate("Dependencies can't be satisfied for the following packages:"))
        logger.debug("{}{}", " " * 12, " ".join(pkg_names))
        logger.debug(str(exc))
        for pkg_name in pkg_names:
            try:
                results += PackageDB.get_sync_print_format_output([pkg_name])
            except DependencyError as exc2:
                logger.debug(translate("Because of:"))
                logger.debug(str(exc2))
    return [
        all_repo_pkgs[result.full_name] for result in results
        if result.name in all_local_pkgs
    ]


def find_sysupgrade_packages(
        ignore_pkgs: list[str] | None = None,
        install_pkgs: list[str] | None = None,
) -> list[pyalpm.Package]:
    all_repo_pkgs = PackageDB.get_repo_dict()

    extra_args: list[str] = []
    for excluded_pkg_name in ignore_pkgs or []:
        # pacman's --ignore doesn't work with repo name:
        extra_args.extend(("--ignore", strip_repo_name(excluded_pkg_name)))
    extra_args.extend(
        added_pkg_name
        for added_pkg_name in install_pkgs or []
    )

    logger.debug("Gonna get sysupgrade info...")
    results = PackageDB.get_print_format_output(
        [*get_pacman_command(), "--sync"] +
        ["--sysupgrade"] * parse_args().sysupgrade +
        extra_args,
    )
    return [
        all_repo_pkgs[result.full_name] for result in results
    ]


def find_packages_not_from_repo() -> list[str]:
    repo_pkg_names = PackageDB.get_repo_pkgnames()
    return [
        pkg_name
        for pkg_name in PackageDB.get_local_pkgnames()
        if pkg_name not in repo_pkg_names
    ]


def refresh_pkg_db_if_needed() -> None:
    args = parse_args()
    if args.refresh:
        pacman_args = (sudo(
            [*get_pacman_command(), "--sync"] + ["--refresh"] * args.refresh,
        ))
        retry_interactive_command_or_exit(pacman_args)


def install_built_deps(
        deps_names_and_paths: "dict[str, Path]",
        resolved_conflicts: list[list[str]] | None = None,
) -> None:
    if not deps_names_and_paths:
        return

    local_packages = PackageDB.get_local_dict()
    args = parse_args()

    def _get_pacman_command() -> list[str]:
        return get_pacman_command() + reconstruct_args(args, ignore_args=[
            "upgrade",
            "asdeps",
            "sync",
            "sysupgrade",
            "refresh",
            "ignore",
            "downloadonly",
        ])

    explicitly_installed_deps = []
    for pkg_name in deps_names_and_paths:
        logger.debug(pkg_name)
        if pkg_name in local_packages and local_packages[pkg_name].reason == 0:
            explicitly_installed_deps.append(pkg_name)
    deps_upgrade_success = True
    if len(explicitly_installed_deps) < len(deps_names_and_paths):
        # @TODO: add support for --skip-failed-build here:
        deps_upgrade_success = retry_interactive_command(
            sudo(
                [*_get_pacman_command(), "--upgrade", "--asdeps"] + [
                    str(path) for name, path in deps_names_and_paths.items()
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
                [*_get_pacman_command(), "--upgrade"] + [
                    str(path) for name, path in deps_names_and_paths.items()
                    if name in explicitly_installed_deps
                ],
            ),
            pikspect=True,
            conflicts=resolved_conflicts,
        )

    PackageDB.discard_local_cache()

    if not (deps_upgrade_success and explicit_upgrade_success):
        raise DependencyError


def strip_repo_name(pkg_name: str) -> str:
    return pkg_name.split(REPO_NAME_DELIMITER, 1)[-1]


def get_ignored_pkgnames_from_patterns(
        orig_pkg_names: list[str],
        ignore_patterns: list[str],
) -> list[str]:
    ignored_pkg_names: list[str] = []
    for pkg_name in orig_pkg_names:
        for ignore_pattern in ignore_patterns:
            if fnmatch.fnmatch(pkg_name, ignore_pattern):
                ignored_pkg_names.append(pkg_name)
                break
    return ignored_pkg_names
