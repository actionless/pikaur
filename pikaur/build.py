import os
import sys
import shutil
from multiprocessing.pool import ThreadPool
from typing import List, Union, Dict, Set, Optional

from .core import (
    DataType,
    isolate_root_cmd, remove_dir, running_as_root, open_file,
    spawn, interactive_spawn, InteractiveSpawn, sudo,
    just_copy_damn_tree as copy_tree,
)
from .i18n import _, _n
from .config import (
    PikaurConfig,
    CACHE_ROOT, AUR_REPOS_CACHE_PATH, BUILD_CACHE_PATH, PACKAGE_CACHE_PATH,
)
from .aur import get_repo_url, find_aur_packages
from .pacman import find_local_packages, PackageDB, get_pacman_command
from .args import PikaurArgs, parse_args
from .pprint import color_line, bold_line, color_enabled, print_stdout
from .prompt import retry_interactive_command, retry_interactive_command_or_exit, ask_to_continue
from .exceptions import (
    CloneError, DependencyError, BuildError, DependencyNotBuiltYet,
    SysExit,
)
from .srcinfo import SrcInfo
from .package_update import is_devel_pkg
from .version import compare_versions
from .pikspect import pikspect
from .makepkg_config import MakepkgConfig


class PackageBuild(DataType):
    # pylint: disable=too-many-instance-attributes
    clone = False
    pull = False

    package_base: str
    package_names: List[str]

    repo_path: str
    build_dir: str
    built_packages_paths: Dict[str, str]

    _already_installed: Optional[bool] = None
    failed: Optional[bool] = None
    reviewed = False
    built_packages_installed: Dict[str, bool]

    new_deps_to_install: List[str]
    new_make_deps_to_install: List[str]
    built_deps_to_install: Dict[str, str]

    args: PikaurArgs

    def __init__(self, package_names: List[str]) -> None:  # pylint: disable=super-init-not-called
        self.args = parse_args()
        self.package_names = package_names
        self.package_base = find_aur_packages([package_names[0]])[0][0].packagebase

        self.repo_path = os.path.join(AUR_REPOS_CACHE_PATH, self.package_base)
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
        return interactive_spawn([
            'git',
            '-C',
            self.repo_path,
            'checkout',
            '--',
            "*"
        ])

    def git_clean(self) -> InteractiveSpawn:
        return interactive_spawn([
            'git',
            '-C',
            self.repo_path,
            'clean',
            '-f',
            '-d',
            '-x'
        ])

    def get_task_command(self) -> List[str]:
        if self.pull:
            return [
                'git',
                '-C',
                self.repo_path,
                'pull',
                'origin',
                'master'
            ]
        elif self.clone:
            return [
                'git',
                'clone',
                get_repo_url(self.package_base),
                self.repo_path,
            ]
        return NotImplemented

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
    def last_installed_hash(self) -> Union[str, None]:
        if self.is_installed:
            with open_file(self.last_installed_file_path) as last_installed_file:
                return last_installed_file.readlines()[0].strip()
        return None

    def update_last_installed_file(self) -> None:
        shutil.copy2(
            os.path.join(
                self.repo_path,
                '.git/refs/heads/master'
            ),
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
    def current_hash(self) -> str:
        with open_file(
            os.path.join(
                self.repo_path,
                '.git/refs/heads/master'
            )
        ) as current_hash_file:
            return current_hash_file.readlines()[0].strip()

    @property
    def version_already_installed(self) -> bool:
        if self._already_installed is None:
            local_db = PackageDB.get_local_dict()
            src_info_dir = self.repo_path
            if is_devel_pkg(self.package_base):
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
                        [
                            'makepkg', '--nobuild', '--noprepare', '--nocheck', '--nodeps'
                        ],
                        cwd=self.build_dir
                    ),
                    cwd=self.build_dir,
                    print_output=False,
                    save_output=True
                )
                if pkgver_result.returncode != 0:
                    sys.stdout.buffer.write(pkgver_result.saved_bytes)
                    sys.stdout.buffer.flush()
                    if not ask_to_continue(
                            args=self.args, default_yes=False
                    ):
                        raise SysExit(125)
                src_info_dir = self.build_dir
                SrcInfo(src_info_dir).regenerate()
            self._already_installed = min([
                compare_versions(
                    local_db[pkg_name].version,
                    SrcInfo(src_info_dir, pkg_name).get_version()
                ) == 0
                if pkg_name in local_db else False
                for pkg_name in self.package_names
            ])
        return self._already_installed

    @property
    def all_deps_to_install(self):
        return self.new_make_deps_to_install + self.new_deps_to_install

    def _get_built_deps(
            self,
            all_package_builds: Dict[str, 'PackageBuild']
    ) -> None:
        self.built_deps_to_install = {}
        for dep in self.all_deps_to_install:
            # @TODO: check if dep is Provided by built package
            if dep not in all_package_builds:
                continue
            package_build = all_package_builds[dep]
            for pkg_name in package_build.package_names:
                if package_build.failed:
                    self.failed = True
                    raise DependencyError()
                if not package_build.built_packages_paths.get(pkg_name):
                    raise DependencyNotBuiltYet()
                if not package_build.built_packages_installed.get(pkg_name):
                    self.built_deps_to_install[pkg_name] = \
                        package_build.built_packages_paths[pkg_name]
                if dep in self.new_make_deps_to_install:
                    self.new_make_deps_to_install.remove(dep)
                if dep in self.new_deps_to_install:
                    self.new_deps_to_install.remove(dep)

    def _install_built_deps(
            self,
            all_package_builds: Dict[str, 'PackageBuild']
    ) -> None:

        if not self.built_deps_to_install:
            return

        print('{} {}:'.format(
            color_line('::', 13),
            _("Installing already built dependencies for {}").format(
                bold_line(', '.join(self.package_names)))
        ))

        local_packages = PackageDB.get_local_dict()
        explicitly_installed_deps = []
        for dep_name in self.built_deps_to_install:
            if dep_name in local_packages and local_packages[dep_name].reason == 0:
                explicitly_installed_deps.append(dep_name)

        result1 = True
        if len(explicitly_installed_deps) < len(self.built_deps_to_install):
            result1 = retry_interactive_command(
                sudo(
                    get_pacman_command(self.args) + [
                        '--upgrade',
                        '--asdeps',
                    ] + [
                        path for name, path in self.built_deps_to_install.items()
                        if name not in explicitly_installed_deps
                    ],
                ),
                args=self.args,
                pikspect=True,
            )
        result2 = True
        if explicitly_installed_deps:
            result2 = retry_interactive_command(
                sudo(
                    get_pacman_command(self.args) + [
                        '--upgrade',
                    ] + [
                        path for name, path in self.built_deps_to_install.items()
                        if name in explicitly_installed_deps
                    ]
                ),
                args=self.args,
                pikspect=True,
            )

        PackageDB.discard_local_cache()

        if result1 and result2:
            for pkg_name in self.built_deps_to_install:
                all_package_builds[pkg_name].built_packages_installed[pkg_name] = True
        else:
            self.failed = True
            raise DependencyError()

    def _set_built_package_path(self) -> None:
        dest_dir = MakepkgConfig.get('PKGDEST', self.build_dir)
        pkg_paths = spawn(
            isolate_root_cmd(['makepkg', '--packagelist'],
                             cwd=self.build_dir),
            cwd=self.build_dir
        ).stdout_text.splitlines()
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
            if not os.path.exists(pkg_path):
                BuildError(_("{} does not exist on the filesystem.").format(pkg_path))
            if dest_dir == self.build_dir:
                pkg_filename = os.path.basename(pkg_path)
                new_package_path = os.path.join(PACKAGE_CACHE_PATH, pkg_filename)
                if not os.path.exists(PACKAGE_CACHE_PATH):
                    os.makedirs(PACKAGE_CACHE_PATH)
                if os.path.exists(new_package_path):
                    os.remove(new_package_path)
                shutil.move(pkg_path, PACKAGE_CACHE_PATH)
                pkg_path = new_package_path
            self.built_packages_paths[pkg_name] = pkg_path

    def prepare_build_destination(self) -> None:
        if running_as_root():
            # Let systemd-run setup the directories and symlinks
            true_cmd = isolate_root_cmd(['true'])
            spawn(true_cmd)
            # Chown the private CacheDirectory to root to signal systemd that
            # it needs to recursively chown it to the correct user
            os.chown(os.path.realpath(CACHE_ROOT), 0, 0)

        if os.path.exists(self.build_dir) and not (
                self.args.keepbuild or PikaurConfig().build.get_bool('KeepBuildDir')
        ):
            remove_dir(self.build_dir)
        copy_tree(self.repo_path, self.build_dir)

    def _get_deps(self) -> None:
        local_provided_pkgs = PackageDB.get_local_provided_dict()
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
                installed_deps, new_deps_to_install = find_local_packages(
                    new_deps_version_matchers.keys()
                )
                # find deps satisfied via provided packages:
                for dep_name in new_deps_to_install[:]:
                    if dep_name not in local_provided_pkgs:
                        continue
                    # and check version of each candidate:
                    for provided_by in local_provided_pkgs[dep_name]:
                        if new_deps_version_matchers[dep_name](provided_by.package.version):
                            new_deps_to_install.remove(dep_name)
                            break
                # check also versions of explicitly satisfied deps:
                new_deps_to_install += [
                    pkg.name
                    for pkg in installed_deps
                    if not new_deps_version_matchers[pkg.name](pkg.version)
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
        print('{} {}:'.format(
            color_line('::', 13),
            _("Installing repository dependencies for {}").format(
                bold_line(', '.join(self.package_names)))
        ))
        retry_interactive_command_or_exit(
            sudo(
                get_pacman_command(self.args) + [
                    '--sync',
                    '--asdeps',
                ] + self.all_deps_to_install
            ),
            args=self.args,
            pikspect=True,
        )
        PackageDB.discard_local_cache()
        return local_packages_before

    def _remove_repo_deps(self, local_packages_before: Set[str]) -> None:
        if not self.all_deps_to_install:
            return
        PackageDB.discard_local_cache()
        local_packages_after = set(PackageDB.get_local_dict().keys())

        deps_packages_installed = local_packages_after.difference(local_packages_before)
        deps_packages_removed = local_packages_before.difference(local_packages_after)
        if deps_packages_removed:
            print('{} {}:'.format(
                color_line(':: error', 9),
                _("Failed to remove installed dependencies, packages inconsistency: {}").format(
                    bold_line(', '.join(deps_packages_removed)))
            ))
            if not ask_to_continue(args=self.args):
                sys.exit(125)
        if not deps_packages_installed:
            return

        print('{} {}:'.format(
            color_line('::', 13),
            _("Removing installed repository dependencies for {}").format(
                bold_line(', '.join(self.package_names)))
        ))
        retry_interactive_command_or_exit(
            sudo(
                get_pacman_command(self.args) + [
                    '--remove',
                ] + list(deps_packages_installed)
            ),
            args=self.args,
            pikspect=True,
        )
        PackageDB.discard_local_cache()

    def build(
            self, all_package_builds: Dict[str, 'PackageBuild']
    ) -> None:

        self.prepare_build_destination()
        self._get_deps()
        self._get_built_deps(all_package_builds)
        self._install_built_deps(all_package_builds)
        local_packages_before = self._install_repo_deps()

        makepkg_args = []
        if not self.args.needed:
            makepkg_args.append('--force')
        if not color_enabled():
            makepkg_args.append('--nocolor')
        print()
        build_succeeded = retry_interactive_command(
            isolate_root_cmd(
                [
                    'makepkg',
                ] + makepkg_args,
                cwd=self.build_dir
            ),
            cwd=self.build_dir,
            args=self.args,
            pikspect=True,
        )
        print()

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
    with ThreadPool() as pool:
        requests = {
            key: pool.apply_async(spawn, (repo_status.get_task_command(), ))
            for key, repo_status in package_builds_by_name.items()
        }
        pool.close()
        pool.join()
        for package_name, request in requests.items():
            result = request.get()
            if result.returncode > 0:
                raise CloneError(
                    build=package_builds_by_name[package_name],
                    result=result
                )
    return package_builds_by_name
