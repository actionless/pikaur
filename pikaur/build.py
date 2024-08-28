"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
# pylint: disable=too-many-lines

import os
import shutil
from glob import glob
from multiprocessing.pool import ThreadPool
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from .args import parse_args
from .aur import find_aur_packages, get_repo_url
from .config import (
    DECORATION,
    AurReposCachePath,
    BuildCachePath,
    BuildDepsLockPath,
    PackageCachePath,
    PikaurConfig,
    UsingDynamicUsers,
)
from .exceptions import (
    BuildError,
    CloneError,
    DependencyError,
    DependencyNotBuiltYetError,
    SkipBuildError,
    SysExit,
)
from .filelock import FileLock
from .i18n import translate, translate_many
from .logging_extras import create_logger
from .makepkg_config import MakePkgCommand, MakepkgConfig, get_pkgdest
from .os_utils import (
    chown_to_current,
    dirname,
    mkdir,
    open_file,
    remove_dir,
    replace_file,
)
from .pacman import PackageDB, get_pacman_command, install_built_deps
from .pikaprint import (
    ColorsHighlight,
    TTYRestoreContext,
    bold_line,
    color_enabled,
    color_line,
    print_error,
    print_stderr,
    print_stdout,
)
from .pikatypes import DataType
from .privilege import (
    isolate_root_cmd,
    sudo,
)
from .prompt import (
    ask_to_continue,
    get_editor_or_exit,
    get_input,
    retry_interactive_command_or_exit,
)
from .spawn import (
    PIPE,
    interactive_spawn,
    joined_spawn,
    spawn,
)
from .srcinfo import SrcInfo
from .updates import is_devel_pkg
from .urllib_helper import wrap_proxy_env
from .version import VersionMatcher, compare_versions

if TYPE_CHECKING:
    from typing import Final

    from .args import PikaurArgs
    from .pacman import ProvidedDependency
    from .spawn import InteractiveSpawn, SpawnArgs

logger = create_logger("build")

DEFAULT_PKGBUILD_BASENAME: "Final" = "PKGBUILD"
ARCH_ANY: "Final" = "any"
IGNORE_PATHS_WHEN_COPYING: "Final[tuple[str]]" = (".git", )


class PkgbuildChanged(Exception):  # noqa: N818
    pass


def _shell(cmds: list[str]) -> "InteractiveSpawn":
    return interactive_spawn(isolate_root_cmd(wrap_proxy_env(cmds)))


def isolated_mkdir(to_path: Path) -> None:
    mkdir_result = spawn(isolate_root_cmd(["mkdir", "-p", str(to_path)]))
    if mkdir_result.returncode != 0:
        print_stdout(mkdir_result.stdout_text)
        print_stderr(mkdir_result.stderr_text)
        raise RuntimeError(translate(f"Can't create destination directory '{to_path}'."))


def copy_aur_repo(from_path: Path, to_path: Path) -> None:
    from_path = from_path.resolve()
    to_path = to_path.resolve()
    if not to_path.exists():
        isolated_mkdir(to_path)

    from_paths = []
    for src_path_str in glob(f"{from_path}/*") + glob(f"{from_path}/.*"):  # noqa: PTH207
        src_path = Path(src_path_str)
        if src_path.name not in IGNORE_PATHS_WHEN_COPYING:
            from_paths.append(src_path)
    to_path = to_path.parent / f"{to_path.name}/"

    cmd_args = isolate_root_cmd(["cp", "-r", *[str(path) for path in [*from_paths, to_path]]])

    result = spawn(cmd_args)
    if result.returncode != 0:
        if to_path.exists():
            remove_dir(to_path)
            isolated_mkdir(to_path)
        result = interactive_spawn(cmd_args)
        if result.returncode != 0:
            raise RuntimeError(translate(f"Can't copy '{from_path}' to '{to_path}'."))


class PackageBuild(DataType):  # noqa: PLR0904
    # pylint: disable=too-many-instance-attributes
    clone = False
    pull = False

    package_base: str
    package_names: list[str]
    provides: list[str]

    repo_path: Path
    pkgbuild_path: Path
    build_dir: Path
    build_gpgdir: str
    built_packages_paths: dict[str, Path]

    reviewed = False
    keep_build_dir = False
    skip_carch_check = False
    _source_repo_updated = False
    _build_files_copied = False

    failed: bool | None = None

    new_deps_to_install: list[str]
    new_make_deps_to_install: list[str]
    built_deps_to_install: dict[str, Path]

    args: "PikaurArgs"
    resolved_conflicts: list[list[str]] | None = None

    _local_pkgs_wo_build_deps: set[str]
    _local_pkgs_with_build_deps: set[str]
    _local_provided_pkgs_with_build_deps: dict[str, list["ProvidedDependency"]]

    def __repr__(self) -> str:
        return (
            f'<{self.__class__.__name__} "{self.package_base}" '
            f"{self.package_names}>"
        )

    def __init__(  # pylint: disable=super-init-not-called
            self,
            package_names: list[str] | None = None,
            pkgbuild_path: str | None = None,
    ) -> None:
        self.args = parse_args()

        if pkgbuild_path:
            self.repo_path = dirname(pkgbuild_path)
            self.pkgbuild_path = Path(pkgbuild_path)
            srcinfo = SrcInfo(pkgbuild_path=pkgbuild_path)
            srcinfo.regenerate()  # @TODO: this is a workaround for building
            # multiple PKGBUILDs from the same directory, find some better way.
            pkgbase = srcinfo.get_value("pkgbase")
            if pkgbase and srcinfo.pkgnames:
                self.package_names = package_names or srcinfo.pkgnames
                self.package_base = pkgbase
                self.provides = srcinfo.get_values("provides")
            else:
                no_pkgname_error = translate("Can't get package name from PKGBUILD")
                raise BuildError(message=no_pkgname_error, build=self)
        elif package_names:
            self.package_names = package_names
            aur_pkg = find_aur_packages([package_names[0]])[0][0]
            self.package_base = aur_pkg.packagebase
            self.provides = aur_pkg.provides
            self.repo_path = AurReposCachePath() / self.package_base
            self.pkgbuild_path = self.repo_path / DEFAULT_PKGBUILD_BASENAME
        else:
            missing_property_error = translate(
                "Either `{prop1}` or `{prop2}` should be set",
            ).format(
                prop1="package_names",
                prop2="pkgbuild_path",
            )
            raise NotImplementedError(missing_property_error)

        self.build_dir = BuildCachePath() / self.package_base
        logger.debug("Build dir: {}", self.build_dir)
        self.build_gpgdir = self.args.build_gpgdir
        self.built_packages_paths = {}
        self.keep_build_dir = self.args.keepbuild or (
            is_devel_pkg(self.package_base) and PikaurConfig().build.KeepDevBuildDir.get_bool()
        )
        self.skip_carch_check = PikaurConfig().build.IgnoreArch.get_bool()

        if self.repo_path.exists():
            if (self.repo_path / ".git").exists():
                self.pull = True
            else:
                self.clone = True
        else:
            isolated_mkdir(self.repo_path)
            self.clone = True

        self.reviewed = self.current_hash == self.last_installed_hash

        self._local_pkgs_wo_build_deps = set()
        self._local_pkgs_with_build_deps = set()
        self._local_provided_pkgs_with_build_deps = {}

    def git_diff(self) -> "InteractiveSpawn":
        return _shell([
            "git",
            "-C", str(self.repo_path),
            "diff",
        ])

    def git_reset_changed(self) -> "InteractiveSpawn":
        return _shell([
            "git",
            "-C", str(self.repo_path),
            "checkout",
            "--",
            "*",
        ])

    def git_stash(self) -> "InteractiveSpawn":
        return _shell([
            "git",
            "-C", str(self.repo_path),
            "stash",
        ])

    def git_stash_pop(self) -> "InteractiveSpawn":
        return _shell([
            "git",
            "-C", str(self.repo_path),
            "stash",
            "pop",
        ])

    def update_aur_repo(self) -> "InteractiveSpawn | None":
        cmd_args: list[str] | None = None
        if self.pull and not self.args.skip_aur_pull:
            cmd_args = [
                "git",
                "-C", str(self.repo_path),
                "pull",
                "origin",
                "master",
            ]
        if self.clone:
            cmd_args = [
                "git",
                "clone",
                get_repo_url(self.package_base),
                str(self.repo_path),
            ]
        result: InteractiveSpawn | None = None
        if cmd_args:
            result = spawn(isolate_root_cmd(wrap_proxy_env(cmd_args)))
        self.reviewed = self.current_hash == self.last_installed_hash
        return result

    @property
    def last_installed_file_path(self) -> Path:
        return self.repo_path / "last_installed.txt"

    @property
    def last_installed_hash(self) -> str | None:
        """Commit hash of AUR repo of last version of the pkg installed by Pikaur."""
        if self.last_installed_file_path.exists():
            with open_file(self.last_installed_file_path) as last_installed_file:
                lines = last_installed_file.readlines()
                if lines:
                    return lines[0].strip()
        return None

    def update_last_installed_file(self) -> None:
        git_hash_path = self.repo_path / ".git/refs/heads/master"
        if git_hash_path.exists():
            shutil.copy2(
                git_hash_path,
                self.last_installed_file_path,
            )
            chown_to_current(self.last_installed_file_path)

    @property
    def current_hash(self) -> str | None:
        """Commit hash of AUR repo of the pkg."""
        git_hash_path = self.repo_path / ".git/refs/heads/master"
        if not git_hash_path.exists():
            return None
        with open_file(git_hash_path) as current_hash_file:
            return current_hash_file.readlines()[0].strip()

    def get_latest_dev_sources(
            self, *, check_dev_pkgs: bool = True, tty_restore: bool = False,
    ) -> None:
        if not self.reviewed:
            return
        self.prepare_build_destination()
        if (
                self._source_repo_updated
        ) or (
            not (is_devel_pkg(self.package_base) and check_dev_pkgs)
        ):
            return
        message = translate_many(
            "Downloading the latest sources for a devel package {}",
            "Downloading the latest sources for devel packages {}",
            len(self.package_names),
        ).format(
            bold_line(", ".join(self.package_names)),
        )
        print_stdout(
            f"{color_line(DECORATION, ColorsHighlight.white)} {message}...",
            tty_restore=tty_restore,
        )
        pkgver_result = joined_spawn(
            isolate_root_cmd(
                [*MakePkgCommand.get(), "--nobuild", "--nocheck", "--nodeps"],
                cwd=self.build_dir,
            ),
            cwd=self.build_dir,
        )
        if pkgver_result.returncode != 0:
            error_text = translate("failed to retrieve latest dev sources:")
            print_stderr(tty_restore=tty_restore)
            print_stderr(tty_restore=tty_restore)
            print_error(error_text, tty_restore=tty_restore)
            print_stderr(pkgver_result.stdout_text, tty_restore=tty_restore)

            if self.args.skip_failed_build:
                answer = translate("s")
            elif self.args.noconfirm:
                answer = translate("a")
            else:  # pragma: no cover
                prompt = "{} {}\n{}\n> ".format(
                    color_line(DECORATION, ColorsHighlight.yellow),
                    translate("Try recovering?"),
                    "\n".join((
                        translate("[R] retry clone"),
                        translate("[d] delete build dir and try again"),
                        translate("[e] edit PKGBUILD"),
                        translate("[i] ignore the error"),
                        "-" * 24,
                        translate("[s] skip building this package"),
                        translate("[a] abort building all the packages"),
                    )),
                )
                answer = get_input(
                    prompt,
                    translate("r").upper() +
                    translate("d") +
                    translate("e") +
                    translate("i") +
                    translate("s") +
                    translate("a"),
                )

            answer = answer.lower()[0]
            if answer == translate("r"):  # pragma: no cover
                self.get_latest_dev_sources(check_dev_pkgs=check_dev_pkgs)
                return
            if answer == translate("d"):  # pragma: no cover
                self.prepare_build_destination(flush=True)
                self.get_latest_dev_sources(check_dev_pkgs=check_dev_pkgs)
                return
            if answer == translate("e"):  # pragma: no cover
                editor_cmd = get_editor_or_exit()
                if editor_cmd:
                    interactive_spawn(
                        [*editor_cmd, str(self.pkgbuild_path)],
                    )
                    interactive_spawn(isolate_root_cmd([
                        "cp",
                        str(self.pkgbuild_path),
                        str(self.build_dir / DEFAULT_PKGBUILD_BASENAME),
                    ]))
                    raise PkgbuildChanged
                self.get_latest_dev_sources(check_dev_pkgs=check_dev_pkgs)
                return
            if answer == translate("i"):
                return
            if answer == translate("a"):
                raise SysExit(125)
            # "s"kip
            raise SkipBuildError(message=error_text, build=self)
        SrcInfo(self.build_dir).regenerate()
        self._source_repo_updated = True

    def get_version(self, package_name: str) -> str:
        return SrcInfo(self.build_dir, package_name).get_version()

    def _compare_versions(self, compare_to: int) -> bool:
        local_db = PackageDB.get_local_dict()
        self.get_latest_dev_sources(check_dev_pkgs=self.args.needed)
        return min(
            compare_versions(
                local_db[pkg_name].version,
                self.get_version(pkg_name),
            ) == compare_to
            if pkg_name in local_db else False
            for pkg_name in self.package_names
        )

    @property
    def version_already_installed(self) -> bool:
        return self._compare_versions(0)

    @property
    def version_is_upgradeable(self) -> bool:
        return self._compare_versions(-1)

    @property
    def all_deps_to_install(self) -> list[str]:
        return self.new_make_deps_to_install + self.new_deps_to_install

    def _filter_built_deps(
            self,
            all_package_builds: dict[str, "PackageBuild"],
    ) -> None:
        logger.debug("<< _FILTER_BUILT_DEPS")

        def _mark_dep_resolved(dep: str) -> None:
            logger.debug("  _mark_dep_resolved: {}", dep)
            if dep in self.new_make_deps_to_install:
                self.new_make_deps_to_install.remove(dep)
            if dep in self.new_deps_to_install:
                self.new_deps_to_install.remove(dep)

        all_provided_pkgnames: dict[str, str] = {}
        for pkg_build in all_package_builds.values():
            for pkg_name in pkg_build.package_names:
                srcinfo = SrcInfo(
                    pkgbuild_path=pkg_build.pkgbuild_path, package_name=pkg_name,
                )
                stripped_pkg_name = VersionMatcher(pkg_name).pkg_name
                all_provided_pkgnames.update(
                    dict.fromkeys(
                        [stripped_pkg_name, *(
                            VersionMatcher(name).pkg_name
                            for name in srcinfo.get_values("provides")
                        )],
                        stripped_pkg_name,
                    ),
                )

        self.built_deps_to_install = {}

        logger.debug("  self.all_deps_to_install={}", self.all_deps_to_install)
        logger.debug("  all_provided_pkgnames={}", all_provided_pkgnames)
        for dep in self.all_deps_to_install:
            dep_name = VersionMatcher(dep).pkg_name
            logger.debug("    {} {}", dep, dep_name)
            if dep_name not in all_provided_pkgnames:
                continue
            package_build = all_package_builds[all_provided_pkgnames[dep_name]]
            logger.debug("    {} {}", package_build, all_provided_pkgnames[dep_name])
            if package_build == self:
                _mark_dep_resolved(dep)
                continue
            for pkg_name in package_build.package_names:
                logger.debug("      {}", pkg_name)
                if package_build.failed:
                    self.failed = True
                    logger.debug("      FAILED")
                    raise DependencyError
                if not package_build.built_packages_paths.get(pkg_name):
                    logger.debug("      NOT_BUILT: {}", package_build.built_packages_paths)
                    raise DependencyNotBuiltYetError
                self.built_deps_to_install[pkg_name] = \
                    package_build.built_packages_paths[pkg_name]
                _mark_dep_resolved(dep)
        logger.debug(">> _FILTER_BUILT_DEPS")

    def _get_pacman_command(self, ignore_args: list[str] | None = None) -> list[str]:
        return get_pacman_command(ignore_args=ignore_args) + (
            ["--noconfirm"] if self.args.noconfirm else []
        )

    def install_built_deps(
            self,
            all_package_builds: dict[str, "PackageBuild"],
    ) -> None:

        self.get_deps(all_package_builds)
        if not self.built_deps_to_install:
            return

        message = translate("Installing already built dependencies for {}").format(
            bold_line(", ".join(self.package_names)),
        )
        print_stderr(f"{color_line(DECORATION, ColorsHighlight.purple)} {message}:")

        try:
            update_self_deps = False
            for pkg_name, pkg_build in all_package_builds.items():
                if pkg_name in self.built_deps_to_install:
                    pkg_build.install_built_deps(all_package_builds)
                    update_self_deps = True
            if update_self_deps:
                self.get_deps(all_package_builds)
            install_built_deps(
                deps_names_and_paths=self.built_deps_to_install,
                resolved_conflicts=self.resolved_conflicts,
            )
        except DependencyError as dep_exc:
            self.failed = True
            raise dep_exc from None
        finally:
            PackageDB.discard_local_cache()

    def set_built_package_path(self) -> None:
        pkg_paths_spawn = spawn(
            isolate_root_cmd(
                [*MakePkgCommand.get(), "--packagelist"],
                cwd=self.build_dir,
            ),
            cwd=self.build_dir,
        )
        if pkg_paths_spawn.returncode != 0:
            return
        if not pkg_paths_spawn.stdout_text:
            return
        logger.debug("Package names: {}", pkg_paths_spawn)
        pkg_paths = [Path(line) for line in pkg_paths_spawn.stdout_text.splitlines()]
        if not pkg_paths:
            return
        pkg_dest = get_pkgdest()
        logger.debug("PKGDEST: {}", pkg_dest)
        pkg_paths.sort(key=lambda x: len(str(x)))
        for pkg_name in self.package_names:
            pkg_path = pkg_paths[0]
            if len(pkg_paths) > 1:
                arch = MakepkgConfig.get("CARCH")
                for each_path in pkg_paths:
                    each_filename = Path(each_path).name
                    if pkg_name in each_filename and (
                            (f"-{arch}." in each_filename) or (f"-{ARCH_ANY}." in each_filename)
                    ):
                        pkg_path = Path(each_filename)
                        break
            pkg_basename = Path(pkg_path).name
            logger.debug("Full path: {}, base path: {}", pkg_path, pkg_basename)
            if pkg_path == Path(pkg_basename):
                pkg_path = (
                    Path(pkg_dest) if pkg_dest else self.build_dir
                ) / pkg_path
                logger.debug("Resolving full path: {} from base path: {}", pkg_path, pkg_basename)
            new_package_path = (
                Path(pkg_dest) if pkg_dest else PackageCachePath()
            ) / pkg_basename
            logger.debug("New package path: {}", new_package_path)
            if not pkg_dest or MakePkgCommand.pkgdest_skipped:
                pkg_sig_path = pkg_path.parent / (pkg_path.name + ".sig")
                new_package_sig_path = new_package_path.parent / (
                    new_package_path.name + ".sig"
                )
                mkdir(PackageCachePath())
                replace_file(pkg_path, new_package_path)
                replace_file(pkg_sig_path, new_package_sig_path)
            pkg_path = new_package_path
            if pkg_path and pkg_path.exists():
                self.built_packages_paths[pkg_name] = pkg_path

    def check_if_already_built(self) -> bool:
        self.get_latest_dev_sources()
        self.set_built_package_path()
        if (
                not self.args.rebuild and
                len(self.built_packages_paths) == len(self.package_names)
        ):
            message = translate_many(
                "Package {pkg} is already built. Pass '--rebuild' flag to force the build.",
                "Packages {pkg} are already built. Pass '--rebuild' flag to force the build.",
                len(self.package_names),
            ).format(
                pkg=bold_line(", ".join(self.package_names)),
            )
            print_stderr(f"{color_line(DECORATION, ColorsHighlight.green)} {message}\n")
            return True
        return False

    def prepare_build_destination(self, *, flush: bool = False) -> None:
        if flush:
            remove_dir(self.build_dir)
            self._build_files_copied = False
        if self._build_files_copied:
            return
        if self.build_dir.exists() and not self.keep_build_dir:
            remove_dir(self.build_dir)
        copy_aur_repo(self.repo_path, self.build_dir)

        pkgbuild_name = self.pkgbuild_path.name
        if pkgbuild_name != DEFAULT_PKGBUILD_BASENAME:
            default_pkgbuild_path = self.build_dir / DEFAULT_PKGBUILD_BASENAME
            custom_pkgbuild_path = self.build_dir / pkgbuild_name
            if default_pkgbuild_path.exists():
                default_pkgbuild_path.unlink()
            os.renames(custom_pkgbuild_path, default_pkgbuild_path)
        self._build_files_copied = True

    def get_deps(
            self,
            all_package_builds: dict[str, "PackageBuild"],
            *,
            filter_built: bool = True,
            exclude_pkg_names: list[str] | None = None,
    ) -> None:
        exclude_pkg_names = exclude_pkg_names or []
        self.new_deps_to_install = []
        new_make_deps_to_install: list[str] = []
        new_check_deps_to_install: list[str] = []
        for package_name in self.package_names:
            if package_name in exclude_pkg_names:
                continue
            src_info = SrcInfo(pkgbuild_path=self.pkgbuild_path, package_name=package_name)
            for new_deps_version_matchers, deps_destination in (
                    (
                        src_info.get_build_depends(), self.new_deps_to_install,
                    ), (
                        src_info.get_build_makedepends(), new_make_deps_to_install,
                    ), (
                        src_info.get_build_checkdepends(), new_check_deps_to_install,
                    ),
            ):
                # find deps satisfied explicitly:
                new_deps_to_install = [
                    dep_line
                    for dep_lines in [
                        new_deps_version_matchers[dep_name].line.split(",")
                        for dep_name in PackageDB.get_not_found_local_packages([
                            vm.line for vm in new_deps_version_matchers.values()
                        ])
                    ]
                    for dep_line in dep_lines
                ]
                deps_destination += new_deps_to_install  # noqa: PLW2901
        self.new_make_deps_to_install = list(set(
            new_make_deps_to_install + new_check_deps_to_install,
        ))
        if filter_built:
            self._filter_built_deps(all_package_builds)

    def _install_repo_deps(self) -> None:
        if not self.all_deps_to_install:
            return

        message = translate("Installing repository dependencies for {}").format(
            bold_line(", ".join(self.package_names)),
        )
        print_stderr(f"{color_line(DECORATION, ColorsHighlight.purple)} {message}:")

        # @TODO: add support for --skip-failed-build here:
        retry_interactive_command_or_exit(
            sudo([
                *self._get_pacman_command(),
                "--sync", "--asdeps",
                *self.all_deps_to_install,
            ]),
            pikspect=True,
            conflicts=self.resolved_conflicts,
        )

    def install_all_deps(self, all_package_builds: dict[str, "PackageBuild"]) -> None:
        with FileLock(BuildDepsLockPath()):
            self.get_deps(all_package_builds)
            if self.all_deps_to_install or self.built_deps_to_install:
                PackageDB.discard_local_cache()
                self._local_pkgs_wo_build_deps = set(PackageDB.get_local_dict().keys())
            self.install_built_deps(all_package_builds)
            self._install_repo_deps()
            PackageDB.discard_local_cache()
            self._local_pkgs_with_build_deps = set(PackageDB.get_local_dict().keys())
            self._local_provided_pkgs_with_build_deps = PackageDB.get_local_provided_dict()

    def _remove_installed_deps(self) -> None:
        # logger.debug(
        #     "Local pkgs before installing build deps: {}", self._local_pkgs_wo_build_deps,
        # )
        if not self._local_pkgs_wo_build_deps:
            return

        logger.debug("Gonna compute diff of installed pkgs")
        deps_packages_installed = self._local_pkgs_with_build_deps.difference(
            self._local_pkgs_wo_build_deps,
        )
        deps_packages_removed = self._local_pkgs_wo_build_deps.difference(
            self._local_pkgs_with_build_deps,
        )
        logger.debug("Deps installed: {}", deps_packages_installed)
        logger.debug("Deps removed: {}", deps_packages_removed)
        if not deps_packages_installed:
            return

        # check if there is diff incosistency because of the package replacement:
        if deps_packages_removed:
            for removed_pkg_name in list(deps_packages_removed):
                for installed_pkg_name in list(deps_packages_installed):
                    if (
                            removed_pkg_name in self._local_provided_pkgs_with_build_deps
                    ) and (
                        installed_pkg_name
                        in [
                            dep.name for dep
                            in self._local_provided_pkgs_with_build_deps[removed_pkg_name]
                        ]
                    ):
                        deps_packages_installed.remove(installed_pkg_name)
                        deps_packages_removed.remove(removed_pkg_name)
                        continue

        if deps_packages_removed:
            error_text = translate(
                "Failed to remove installed dependencies, packages inconsistency: {}",
            ).format(
                bold_line(", ".join(deps_packages_removed)),
            )
            print_error(error_text)
            if not ask_to_continue():
                raise DependencyError(error_text)
        if not deps_packages_installed or self.args.keepbuilddeps:
            return

        message = translate("Removing already installed dependencies for {}").format(
            bold_line(", ".join(self.package_names)),
        )
        print_stderr(f"{color_line(DECORATION, ColorsHighlight.purple)} {message}:")
        retry_interactive_command_or_exit(
            sudo(
                # pacman --remove flag conflicts with some --sync options:
                [
                    *self._get_pacman_command(ignore_args=["overwrite"]),
                    "--remove",
                    *list(deps_packages_installed),
                ],
            ),
            pikspect=True,
        )
        PackageDB.discard_local_cache()

    def check_pkg_arch(self) -> None:
        if self.skip_carch_check:
            return

        src_info = SrcInfo(pkgbuild_path=self.pkgbuild_path)
        arch = MakepkgConfig.get("CARCH")
        supported_archs = src_info.get_values("arch")
        if supported_archs and (
                ARCH_ANY not in supported_archs
        ) and (
            arch not in supported_archs
        ):
            error_text = translate(
                "{name} can't be built on the current arch ({arch}). "
                "Supported: {suparch}",
            ).format(
                name=bold_line(", ".join(self.package_names)),
                arch=arch,
                suparch=", ".join(supported_archs),
            )
            print_error(error_text)
            if (
                    not self.args.skip_failed_build
            ) and (
                not ask_to_continue(default_yes=False)
            ):
                raise BuildError(message=error_text, build=self)
            self.skip_carch_check = True

    def _run_makepkg_cmd(
            self,
            makepkg_args: list[str],
            *,
            skip_pgp_check: bool,
            skip_file_checksums: bool,
            skip_check: bool,
            no_prepare: bool,
    ) -> "InteractiveSpawn":
        cmd_args = MakePkgCommand.get() + makepkg_args
        if skip_pgp_check:
            cmd_args += ["--skippgpcheck"]
        if skip_file_checksums:
            cmd_args += ["--skipchecksums"]
        if self.skip_carch_check:
            cmd_args += ["--ignorearch"]
        if skip_check:
            cmd_args += ["--nocheck"]
        if no_prepare:
            cmd_args += ["--noprepare"]

        env = {}
        if self.build_gpgdir:
            env["GNUPGHOME"] = self.build_gpgdir

        cmd_args = isolate_root_cmd(cmd_args, cwd=self.build_dir, env=env)
        spawn_kwargs: SpawnArgs = {
            "cwd": str(self.build_dir),
            "env": {**os.environ, **env},
        }
        if self.args.hide_build_log:
            spawn_kwargs.update({
                "stdout": PIPE,
                "stderr": PIPE,
            })

        result = interactive_spawn(
            cmd_args,
            **spawn_kwargs,
        )
        print_stdout()
        return result

    def build_with_makepkg(  # pylint: disable=too-many-branches,too-many-statements
            self,
            *,
            skip_check: bool = False,
    ) -> bool:
        makepkg_args = []
        if not self.args.needed:
            makepkg_args.append("--force")
        if not color_enabled():
            makepkg_args.append("--nocolor")

        message = translate("Starting the build")
        print_stderr(
            f"\n{color_line(DECORATION, ColorsHighlight.purple)} {message}:",
        )
        build_succeeded = False
        skip_pgp_check = False
        skip_file_checksums = False
        no_prepare = False
        while True:
            result = self._run_makepkg_cmd(
                makepkg_args=makepkg_args,
                skip_pgp_check=skip_pgp_check,
                skip_file_checksums=skip_file_checksums,
                skip_check=skip_check,
                no_prepare=no_prepare,
            )
            build_succeeded = result.returncode == 0
            if build_succeeded:
                break

            print_stderr(
                color_line(
                    translate("Command '{}' failed to execute.").format(
                        " ".join(str(a) for a in result.args)
                        if isinstance(result.args, list)
                        else result.args,
                    ),
                    ColorsHighlight.red,
                ),
            )
            if self.args.skip_failed_build:
                answer = translate("s")
            elif self.args.noconfirm:
                answer = translate("a")
            else:  # pragma: no cover
                prompt = "{} {}\n{}\n> ".format(
                    color_line(DECORATION, ColorsHighlight.yellow),
                    translate("Try recovering?"),
                    "\n".join((
                        translate("[R] retry build"),
                        translate("[p] PGP check skip"),
                        translate("[c] checksums skip"),
                        translate("[f] skip 'check()' function of PKGBUILD"),
                        translate("[n] skip 'prepare()' function of PKGBUILD"),
                        translate("[i] ignore architecture"),
                        translate("[d] delete build dir and try again"),
                        translate("[e] edit PKGBUILD"),
                        "-" * 24,
                        translate("[s] skip building this package"),
                        translate("[a] abort building all the packages"),
                    )),
                )
                answer = get_input(
                    prompt,
                    translate("r").upper() +
                    translate("p") +
                    translate("c") +
                    translate("f") +
                    translate("n") +
                    translate("i") +
                    translate("d") +
                    translate("e") +
                    translate("s") +
                    translate("a"),
                )

            answer = answer.lower()[0]
            if answer == translate("r"):  # pragma: no cover
                continue
            if answer == translate("p"):  # pragma: no cover
                skip_pgp_check = True
                continue
            if answer == translate("c"):  # pragma: no cover
                skip_file_checksums = True
                continue
            if answer == translate("f"):  # pragma: no cover
                skip_check = True
                continue
            if answer == translate("n"):  # pragma: no cover
                no_prepare = True
                continue
            if answer == translate("i"):  # pragma: no cover
                self.skip_carch_check = True
                continue
            if answer == translate("d"):  # pragma: no cover
                self.prepare_build_destination(flush=True)
                continue
            if answer == translate("e"):  # pragma: no cover
                editor_cmd = get_editor_or_exit()
                if editor_cmd:
                    interactive_spawn(
                        [*editor_cmd, str(self.pkgbuild_path)],
                    )
                    interactive_spawn(isolate_root_cmd([
                        "cp",
                        str(self.pkgbuild_path),
                        str(self.build_dir / DEFAULT_PKGBUILD_BASENAME),
                    ]))
                    raise PkgbuildChanged
                continue
            if answer == translate("a"):
                raise SysExit(125)
            # "s"kip
            break

        return build_succeeded

    def build(
            self,
            all_package_builds: dict[str, "PackageBuild"],
            resolved_conflicts: list[list[str]],
            skip_checkfunc_for_pkgnames: list[str],
    ) -> None:
        self.resolved_conflicts = resolved_conflicts

        self.prepare_build_destination()

        self.install_all_deps(all_package_builds)
        try:
            skip_check = False
            for pkg_name in self.package_names:
                if pkg_name in skip_checkfunc_for_pkgnames:
                    skip_check = True
            build_succeeded = (
                True
                if self.check_if_already_built()
                else self.build_with_makepkg(skip_check=skip_check)
            )
        finally:
            self._remove_installed_deps()

        if not build_succeeded:
            self.failed = True
            raise BuildError(message="failed to build", build=self)
        self.set_built_package_path()


class AlreadyClonedRepos:

    repos: ClassVar[list[str]] = []

    @classmethod
    def add(cls, repo: str) -> None:
        cls.repos.append(repo)

    @classmethod
    def get(cls, repo: str) -> bool:
        return repo in cls.repos


def clone_aur_repos(package_names: list[str]) -> dict[str, PackageBuild]:
    aur_pkgs, _ = find_aur_packages(package_names)
    packages_bases: dict[str, list[str]] = {}
    for aur_pkg in aur_pkgs:
        packages_bases.setdefault(aur_pkg.packagebase, []).append(aur_pkg.name)
    package_builds_by_base = {
        pkgbase: PackageBuild(pkg_names)
        for pkgbase, pkg_names in packages_bases.items()
        if not AlreadyClonedRepos.get(pkgbase)
    }

    pool_size: int | None = None
    if clone_c := parse_args().aur_clone_concurrency:
        pool_size = clone_c
    elif UsingDynamicUsers():
        pool_size = 1
    exc: CloneError | None = None
    with (
            TTYRestoreContext(),
            ThreadPool(processes=pool_size) as pool,
    ):
        requests = {
            key: pool.apply_async(repo_status.update_aur_repo, ())
            for key, repo_status in package_builds_by_base.items()
        }
        pool.close()
        pool.join()
        for package_base, request in requests.items():
            result = request.get()
            if result and result.returncode > 0:
                exc = CloneError(
                    build=package_builds_by_base[package_base],
                    result=result,
                )
            else:
                AlreadyClonedRepos.add(package_base)
    if exc:
        raise exc

    all_package_builds_by_base = {
        pkgbase: PackageBuild(pkg_names)
        for pkgbase, pkg_names in packages_bases.items()
    }
    return {
        pkg_name: all_package_builds_by_base[pkgbase]
        for pkgbase, pkg_names in packages_bases.items()
        for pkg_name in pkg_names
    }
