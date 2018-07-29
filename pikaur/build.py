""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import os
import sys
import shutil
import subprocess
from multiprocessing.pool import ThreadPool
from glob import glob
from typing import List, Dict, Set, Optional, Any

from .core import (
    DataType,
    isolate_root_cmd, remove_dir, open_file, dirname,
    spawn, interactive_spawn, InteractiveSpawn, sudo, running_as_root,
)
from .i18n import _, _n
from .config import (
    PikaurConfig,
    AUR_REPOS_CACHE_PATH, BUILD_CACHE_PATH, PACKAGE_CACHE_PATH,
)
from .aur import get_repo_url, find_aur_packages
from .pacman import (
    PackageDB, get_pacman_command, install_built_deps,
)
from .args import PikaurArgs, parse_args
from .pprint import (
    color_line, bold_line, color_enabled,
    print_stdout, print_stderr, print_error,
)
from .prompt import (
    retry_interactive_command_or_exit, ask_to_continue, get_input,
)
from .exceptions import (
    CloneError, DependencyError, BuildError, DependencyNotBuiltYet,
    SysExit,
)
from .srcinfo import SrcInfo
from .updates import is_devel_pkg
from .version import compare_versions, VersionMatcher
from .pikspect import pikspect
from .makepkg_config import MakepkgConfig, get_makepkg_cmd


def copy_aur_repo(from_path, to_path) -> None:
    from_path = os.path.realpath(from_path)
    to_path = os.path.realpath(to_path)
    if not os.path.exists(to_path):
        spawn(isolate_root_cmd(['mkdir', '-p', to_path]))

    from_paths = []
    for src_path in glob(f'{from_path}/*') + glob(f'{from_path}/.*'):
        if os.path.basename(src_path) != '.git':
            from_paths.append(src_path)
    to_path = f'{to_path}/'

    cmd_args = isolate_root_cmd(['cp', '-r'] + from_paths + [to_path])

    result = spawn(cmd_args)
    if result.returncode != 0:
        if not os.path.exists(to_path):
            remove_dir(to_path)
        result = interactive_spawn(cmd_args)
        if result.returncode != 0:
            raise Exception(_(f"Can't copy '{from_path}' to '{to_path}'."))


class PackageBuild(DataType):
    # pylint: disable=too-many-instance-attributes
    clone = False
    pull = False

    package_base: str
    package_names: List[str]

    repo_path: str
    pkgbuild_path: str
    build_dir: str
    built_packages_paths: Dict[str, str]

    _source_repo_updated = False
    _build_files_copied = False

    failed: Optional[bool] = None
    reviewed = False
    built_packages_installed: Dict[str, bool]

    new_deps_to_install: List[str]
    new_make_deps_to_install: List[str]
    built_deps_to_install: Dict[str, str]

    args: PikaurArgs
    resolved_conflicts: Optional[List[List[str]]] = None

    def __init__(  # pylint: disable=super-init-not-called
            self,
            package_names: Optional[List[str]] = None,
            pkgbuild_path: Optional[str] = None
    ) -> None:
        self.args = parse_args()

        if package_names:
            self.package_names = package_names
            self.package_base = find_aur_packages([package_names[0]])[0][0].packagebase
            self.repo_path = os.path.join(AUR_REPOS_CACHE_PATH, self.package_base)
            self.pkgbuild_path = os.path.join(self.repo_path, 'PKGBUILD')
        elif pkgbuild_path:
            self.repo_path = dirname(pkgbuild_path)
            self.pkgbuild_path = pkgbuild_path
            srcinfo = SrcInfo(pkgbuild_path=pkgbuild_path)
            pkgbase = srcinfo.get_value('pkgbase')
            if pkgbase and srcinfo.pkgnames:
                self.package_names = srcinfo.pkgnames
                self.package_base = pkgbase
            else:
                raise BuildError(_("Can't get package name from PKGBUILD"))
        else:
            raise NotImplementedError('Either `package_names` or `pkgbuild_path` should be set')

        self.build_dir = os.path.join(BUILD_CACHE_PATH, self.package_base)
        self.built_packages_paths = {}
        self.built_packages_installed = {}

        if os.path.exists(self.repo_path):
            # pylint: disable=simplifiable-if-statement
            if os.path.exists(os.path.join(self.repo_path, '.git')):
                self.pull = True
            else:
                self.clone = True
        else:
            os.makedirs(self.repo_path)
            self.clone = True

    def git_reset_changed(self) -> InteractiveSpawn:
        return interactive_spawn(isolate_root_cmd([
            'git',
            '-C',
            self.repo_path,
            'checkout',
            '--',
            "*"
        ]))

    def update_aur_repo(self) -> InteractiveSpawn:
        cmd_args: List[str]
        if self.pull:
            cmd_args = [
                'git',
                '-C',
                self.repo_path,
                'pull',
                'origin',
                'master'
            ]
        if self.clone:
            cmd_args = [
                'git',
                'clone',
                get_repo_url(self.package_base),
                self.repo_path,
            ]
        if not cmd_args:
            return NotImplemented
        return spawn(isolate_root_cmd(cmd_args))

    @property
    def last_installed_file_path(self) -> str:
        return os.path.join(
            self.repo_path,
            'last_installed.txt'
        )

    @property
    def is_installed(self) -> bool:
        return os.path.exists(self.last_installed_file_path)

    @property
    def last_installed_hash(self) -> Optional[str]:
        if self.is_installed:
            with open_file(self.last_installed_file_path) as last_installed_file:
                return last_installed_file.readlines()[0].strip()
        return None

    def update_last_installed_file(self) -> None:
        git_hash_path = os.path.join(
            self.repo_path,
            '.git/refs/heads/master'
        )
        if os.path.exists(git_hash_path):
            shutil.copy2(
                git_hash_path,
                self.last_installed_file_path
            )

    @property
    def build_files_updated(self) -> bool:
        if (
                self.is_installed
        ) and (
            self.last_installed_hash != self.current_hash
        ):
            return True
        return False

    @property
    def current_hash(self) -> Optional[str]:
        git_hash_path = os.path.join(
            self.repo_path,
            '.git/refs/heads/master'
        )
        if not os.path.exists(git_hash_path):
            return None
        with open_file(git_hash_path) as current_hash_file:
            return current_hash_file.readlines()[0].strip()

    def get_latest_dev_sources(self) -> None:
        if self._source_repo_updated:
            return
        if not is_devel_pkg(self.package_base):
            return
        print_stdout('{} {}...'.format(
            color_line('::', 15),
            _n(
                "Downloading the latest sources for a devel package {}",
                "Downloading the latest sources for devel packages {}",
                len(self.package_names)
            ).format(
                bold_line(', '.join(self.package_names))
            )
        ))
        self.prepare_build_destination()
        pkgver_result = pikspect(
            isolate_root_cmd(
                get_makepkg_cmd() + [
                    '--nobuild', '--noprepare', '--nocheck', '--nodeps'
                ],
                cwd=self.build_dir
            ),
            cwd=self.build_dir,
            print_output=False,
            save_output=True,
            auto_proceed=False
        )
        if pkgver_result.returncode != 0:
            sys.stdout.buffer.write(pkgver_result.get_output_bytes())
            sys.stdout.buffer.flush()
            if not ask_to_continue(default_yes=False):
                raise SysExit(125)
        SrcInfo(self.build_dir).regenerate()
        self._source_repo_updated = True

    @property
    def version_already_installed(self) -> bool:
        local_db = PackageDB.get_local_dict()
        self.get_latest_dev_sources()
        return min([
            compare_versions(
                local_db[pkg_name].version,
                SrcInfo(self.build_dir, pkg_name).get_version()
            ) == 0
            if pkg_name in local_db else False
            for pkg_name in self.package_names
        ])

    @property
    def all_deps_to_install(self):
        return self.new_make_deps_to_install + self.new_deps_to_install

    def _get_built_deps(
            self,
            all_package_builds: Dict[str, 'PackageBuild']
    ) -> None:

        def _mark_dep_resolved(dep: str) -> None:
            if dep in self.new_make_deps_to_install:
                self.new_make_deps_to_install.remove(dep)
            if dep in self.new_deps_to_install:
                self.new_deps_to_install.remove(dep)

        self.built_deps_to_install = {}
        for dep in self.all_deps_to_install:
            # @TODO: check if dep is Provided by built package
            dep_name = VersionMatcher(dep).pkg_name
            if dep_name not in all_package_builds:
                continue
            package_build = all_package_builds[dep_name]
            if package_build == self:
                _mark_dep_resolved(dep)
                continue
            for pkg_name in package_build.package_names:
                if package_build.failed:
                    self.failed = True
                    raise DependencyError()
                if not package_build.built_packages_paths.get(pkg_name):
                    raise DependencyNotBuiltYet()
                if not package_build.built_packages_installed.get(pkg_name):
                    self.built_deps_to_install[pkg_name] = \
                        package_build.built_packages_paths[pkg_name]
                _mark_dep_resolved(dep)

    def _get_pacman_command(self) -> List[str]:
        return get_pacman_command() + (['--noconfirm'] if self.args.noconfirm else [])

    def _install_built_deps(
            self,
            all_package_builds: Dict[str, 'PackageBuild']
    ) -> None:

        if not self.built_deps_to_install:
            return

        print_stderr('{} {}:'.format(
            color_line('::', 13),
            _("Installing already built dependencies for {}").format(
                bold_line(', '.join(self.package_names)))
        ))

        try:
            install_built_deps(
                deps_names_and_paths=self.built_deps_to_install,
                resolved_conflicts=self.resolved_conflicts
            )
        except DependencyError as dep_exc:
            self.failed = True
            raise dep_exc from None
        else:
            for pkg_name in self.built_deps_to_install:
                all_package_builds[pkg_name].built_packages_installed[pkg_name] = True

    def _set_built_package_path(self) -> None:
        dest_dir = MakepkgConfig.get('PKGDEST', self.build_dir)
        pkg_paths = spawn(
            isolate_root_cmd(get_makepkg_cmd() + ['--packagelist'],
                             cwd=self.build_dir),
            cwd=self.build_dir
        ).stdout_text.splitlines()
        if not pkg_paths:
            return
        pkg_paths.sort(key=len)
        for pkg_name in self.package_names:
            pkg_path = pkg_paths[0]
            if len(pkg_paths) > 1:
                arch = MakepkgConfig.get('CARCH')
                for each_path in pkg_paths:
                    each_filename = os.path.basename(each_path)
                    if pkg_name in each_filename and (
                            (f'-{arch}.' in each_filename) or ('-any.' in each_filename)
                    ):
                        pkg_path = each_filename
                        break
            pkg_filename = os.path.basename(pkg_path)
            if pkg_path == pkg_filename:
                pkg_path = os.path.join(dest_dir, pkg_path)
            if not os.path.exists(pkg_path):
                BuildError(_("{} does not exist on the filesystem.").format(pkg_path))
            if dest_dir == self.build_dir:
                new_package_path = os.path.join(PACKAGE_CACHE_PATH, pkg_filename)
                if os.path.exists(pkg_path):
                    if not os.path.exists(PACKAGE_CACHE_PATH):
                        os.makedirs(PACKAGE_CACHE_PATH)
                    if os.path.exists(new_package_path):
                        os.remove(new_package_path)
                    shutil.move(pkg_path, PACKAGE_CACHE_PATH)
                pkg_path = new_package_path
            if pkg_path and os.path.exists(pkg_path):
                self.built_packages_paths[pkg_name] = pkg_path

    def check_if_already_built(self) -> bool:
        self.get_latest_dev_sources()
        self._set_built_package_path()
        if (
                not self.args.rebuild and
                len(self.built_packages_paths) == len(self.package_names)
        ):
            print_stderr("{} {}\n".format(
                color_line("::", 10),
                _n(
                    "Package {pkg} is already built. Pass '--rebuild' flag to force the build.",
                    "Packages {pkg} are already built. Pass '--rebuild' flag to force the build.",
                    len(self.package_names)
                ).format(
                    pkg=bold_line(", ".join(self.package_names))
                )
            ))
            return True
        return False

    def prepare_build_destination(self) -> None:
        if self._build_files_copied:
            return
        if os.path.exists(self.build_dir) and not self.args.keepbuild:
            remove_dir(self.build_dir)
        copy_aur_repo(self.repo_path, self.build_dir)

        pkgbuild_name = os.path.basename(self.pkgbuild_path)
        if pkgbuild_name != 'PKGBUILD':
            default_pkgbuild_path = os.path.join(self.build_dir, 'PKGBUILD')
            custom_pkgbuild_path = os.path.join(self.build_dir, pkgbuild_name)
            if os.path.exists(default_pkgbuild_path):
                os.unlink(default_pkgbuild_path)
            os.renames(custom_pkgbuild_path, default_pkgbuild_path)
        self._build_files_copied = True

    def _get_deps(self) -> None:
        self.new_deps_to_install = []
        new_make_deps_to_install: List[str] = []
        new_check_deps_to_install: List[str] = []
        for package_name in self.package_names:
            src_info = SrcInfo(self.build_dir, package_name=package_name)
            for new_deps_version_matchers, deps_destination in (
                    (
                        src_info.get_depends(), self.new_deps_to_install
                    ), (
                        src_info.get_makedepends(), new_make_deps_to_install,
                    ), (
                        src_info.get_checkdepends(), new_check_deps_to_install,
                    ),
            ):
                # find deps satisfied explicitly:
                new_deps_to_install = [
                    dep_line
                    for dep_lines in [
                        new_deps_version_matchers[dep_name].line.split(',')
                        for dep_name in PackageDB.get_not_found_local_packages([
                            vm.line for vm in new_deps_version_matchers.values()
                        ])
                    ]
                    for dep_line in dep_lines
                ]
                deps_destination += new_deps_to_install
        self.new_make_deps_to_install = list(set(
            new_make_deps_to_install + new_check_deps_to_install
        ))

    def _install_repo_deps(self) -> Set[str]:
        if not self.all_deps_to_install:
            return set()
        # @TODO: use lock file?
        PackageDB.discard_local_cache()
        local_packages_before = set(PackageDB.get_local_dict().keys())
        print_stderr('{} {}:'.format(
            color_line('::', 13),
            _("Installing repository dependencies for {}").format(
                bold_line(', '.join(self.package_names)))
        ))
        retry_interactive_command_or_exit(
            sudo(
                self._get_pacman_command() + [
                    '--sync',
                    '--asdeps',
                ] + self.all_deps_to_install
            ),
            pikspect=True,
            conflicts=self.resolved_conflicts,
        )
        PackageDB.discard_local_cache()
        return local_packages_before

    def _remove_repo_deps(self, local_packages_before: Set[str]) -> None:
        if not self.all_deps_to_install:
            return
        PackageDB.discard_local_cache()
        local_packages_after = set(PackageDB.get_local_dict().keys())
        local_provided_pkgs = PackageDB.get_local_provided_dict()

        deps_packages_installed = local_packages_after.difference(local_packages_before)
        deps_packages_removed = local_packages_before.difference(local_packages_after)

        # check if there is diff incosistency because of the package replacement:
        if deps_packages_removed:
            for removed_pkg_name in list(deps_packages_removed):
                for installed_pkg_name in list(deps_packages_installed):
                    if (
                            removed_pkg_name in local_provided_pkgs
                    ) and (installed_pkg_name in local_provided_pkgs[removed_pkg_name]):
                        deps_packages_installed.remove(installed_pkg_name)
                        deps_packages_removed.remove(removed_pkg_name)
                        continue

        if deps_packages_removed:
            print_error(
                _("Failed to remove installed dependencies, packages inconsistency: {}").format(
                    bold_line(', '.join(deps_packages_removed))
                )
            )
            if not ask_to_continue():
                raise SysExit(125)
        if not deps_packages_installed:
            return

        print_stderr('{} {}:'.format(
            color_line('::', 13),
            _("Removing installed repository dependencies for {}").format(
                bold_line(', '.join(self.package_names)))
        ))
        retry_interactive_command_or_exit(
            sudo(
                self._get_pacman_command() + [
                    '--remove',
                ] + list(deps_packages_installed)
            ),
            pikspect=True,
        )
        PackageDB.discard_local_cache()

    def build_with_makepkg(self) -> bool:  # pylint: disable=too-many-branches,too-many-statements
        makepkg_args = []
        if not self.args.needed:
            makepkg_args.append('--force')
        if not color_enabled():
            makepkg_args.append('--nocolor')

        print_stderr('\n{} {}:'.format(
            color_line('::', 13),
            _('Starting the build')
        ))
        build_succeeded = False
        skip_pgp_check = False
        skip_file_checksums = False
        skip_integration_checks = False
        skip_carch_check = False
        while True:
            cmd_args = get_makepkg_cmd() + makepkg_args
            if skip_pgp_check:
                cmd_args += ['--skippgpcheck']
            if skip_file_checksums:
                cmd_args += ['--skipchecksums']
            if skip_integration_checks:
                cmd_args += ['--skipinteg']
            if skip_carch_check:
                cmd_args += ['--ignorearch']
            cmd_args = isolate_root_cmd(cmd_args, cwd=self.build_dir)
            spawn_kwargs: Dict[str, Any] = {}
            if self.args.hide_build_log:
                spawn_kwargs = dict(
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            result = interactive_spawn(
                cmd_args,
                cwd=self.build_dir,
                **spawn_kwargs
            )
            print_stdout()
            build_succeeded = result.returncode == 0
            if build_succeeded:
                break

            print_stderr(color_line(_("Command '{}' failed to execute.").format(
                ' '.join(cmd_args)
            ), 9))
            if PikaurConfig().build.get_bool('SkipFailedBuild'):
                answer = _("s")
            elif self.args.noconfirm:
                answer = _("a")
            else:  # pragma: no cover
                prompt = '{} {}\n{}\n> '.format(
                    color_line('::', 11),
                    _("Try recovering?"),
                    "\n".join((
                        _("[R] retry build"),
                        _("[p] pgp check skip"),
                        _("[c] checksums skip"),
                        _("[i] ignore architecture"),
                        _("[v] skip all validity checks"),
                        "-" * 24,
                        _("[s] skip building this package"),
                        _("[a] abort building all the packages"),
                    ))
                )
                answer = get_input(
                    prompt,
                    _('r').upper() + _('p') + _('c') + _('i') + _('s') + _('a')
                )

            answer = answer.lower()[0]
            if answer == _("r"):
                continue
            elif answer == _("p"):
                skip_pgp_check = True
                continue
            elif answer == _("c"):
                skip_file_checksums = True
                continue
            elif answer == _("i"):
                skip_carch_check = True
                continue
            elif answer == _("v"):
                skip_integration_checks = True
                continue
            elif answer == _("a"):
                raise SysExit(125)
            else:  # "s"kip
                break

        return build_succeeded

    def build(
            self,
            all_package_builds: Dict[str, 'PackageBuild'],
            resolved_conflicts: List[List[str]]
    ) -> None:
        self.resolved_conflicts = resolved_conflicts

        self.prepare_build_destination()

        if self.check_if_already_built():
            return

        self._get_deps()
        self._get_built_deps(all_package_builds)
        self._install_built_deps(all_package_builds)
        local_packages_before = self._install_repo_deps()

        try:
            build_succeeded = self.build_with_makepkg()
        except SysExit as exc:
            self._remove_repo_deps(local_packages_before)
            raise exc

        self._remove_repo_deps(local_packages_before)

        if not build_succeeded:
            self.failed = True
            raise BuildError()
        else:
            self._set_built_package_path()


def clone_aur_repos(package_names: List[str]) -> Dict[str, PackageBuild]:
    aur_pkgs, _ = find_aur_packages(package_names)
    packages_bases: Dict[str, List[str]] = {}
    for aur_pkg in aur_pkgs:
        packages_bases.setdefault(aur_pkg.packagebase, []).append(aur_pkg.name)
    package_builds_by_base = {
        pkgbase: PackageBuild(pkg_names)
        for pkgbase, pkg_names in packages_bases.items()
    }
    package_builds_by_name = {
        pkg_name: package_builds_by_base[pkgbase]
        for pkgbase, pkg_names in packages_bases.items()
        for pkg_name in pkg_names
    }
    pool_size: Optional[int] = None
    if running_as_root():
        pool_size = 1
    with ThreadPool(processes=pool_size) as pool:
        requests = {
            key: pool.apply_async(repo_status.update_aur_repo, ())
            for key, repo_status in package_builds_by_base.items()
        }
        pool.close()
        pool.join()
        for package_base, request in requests.items():
            result = request.get()
            if result.returncode > 0:
                raise CloneError(
                    build=package_builds_by_base[package_base],
                    result=result
                )
    return package_builds_by_name
