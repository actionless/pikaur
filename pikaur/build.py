import os
import shutil
import platform
from typing import List, Union, Dict, Tuple, Any, Optional

from .core import (
    DataType, ConfigReader,
    isolate_root_cmd, remove_dir, running_as_root, open_file,
)
from .async import MultipleTasksExecutor, SingleTaskExecutor
from .async_cmd import CmdTaskWorker, CmdTaskResult
from .i18n import _
from .version import get_package_name_and_version_matcher_from_depend_line, VersionMatcher
from .config import (
    PikaurConfig,
    CACHE_ROOT, AUR_REPOS_CACHE_DIR, BUILD_CACHE_DIR, PACKAGE_CACHE_DIR,
    CONFIG_ROOT,
)
from .aur import get_repo_url, find_aur_packages
from .pacman import find_local_packages, PackageDB, ASK_BITS
from .args import reconstruct_args, PikaurArgs
from .pprint import color_line, bold_line
from .prompt import retry_interactive_command
from .exceptions import (
    CloneError, DependencyError, BuildError, DependencyNotBuiltYet,
)


class SrcInfo():

    _common_lines: List[str] = None
    _package_lines: List[str] = None
    path: str = None
    repo_path: str = None
    package_name: str = None

    def load_config(self) -> None:
        self._common_lines = []
        self._package_lines = []
        destination = self._common_lines
        with open_file(self.path) as srcinfo_file:
            for line in srcinfo_file.readlines():
                if line.startswith('pkgname ='):
                    if line.split('=')[1].strip() == self.package_name:
                        destination = self._package_lines
                    else:
                        destination = []
                else:
                    destination.append(line)

    def __init__(self, repo_path: str, package_name: str = None) -> None:
        self.path = os.path.join(
            repo_path,
            '.SRCINFO'
        )
        self.repo_path = repo_path
        self.package_name = package_name
        self.load_config()

    def get_values(self, field: str) -> List[str]:
        prefix = field + ' = '
        values = []
        for lines in (self._common_lines, self._package_lines):
            for line in lines:
                if line.strip().startswith(prefix):
                    values.append(line.strip().split(prefix)[1])
        return values

    def get_value(self, field: str) -> str:
        return self.get_values(field)[0]

    def get_install_script(self) -> str:
        values = self.get_values('install')
        if values:
            return values[0]
        return None

    def _get_depends(self, field: str) -> List[Tuple[str, VersionMatcher]]:
        dependencies = []
        src_info_pkgname = self.get_value('pkgname')
        for dep in self.get_values(field):
            pkg_name, version_matcher = get_package_name_and_version_matcher_from_depend_line(dep)
            if pkg_name != src_info_pkgname:
                dependencies.append((pkg_name, version_matcher))
        return dependencies

    def get_makedepends(self) -> List[Tuple[str, VersionMatcher]]:
        return self._get_depends('makedepends')

    def get_depends(self) -> List[Tuple[str, VersionMatcher]]:
        return self._get_depends('depends')

    def regenerate(self) -> None:
        with open_file(self.path, 'w') as srcinfo_file:
            result = SingleTaskExecutor(
                CmdTaskWorker(isolate_root_cmd(['makepkg', '--printsrcinfo'],
                                               cwd=self.repo_path),
                              cwd=self.repo_path)
            ).execute()
            srcinfo_file.write(result.stdout)
        self.load_config()


class PackageBaseSrcInfo(SrcInfo):

    def load_config(self) -> None:
        self._common_lines = []
        self._package_lines = []
        with open_file(self.path) as srcinfo_file:
            for line in srcinfo_file.readlines():
                self._common_lines.append(line)


class MakepkgConfig():

    _user_makepkg_path = "unset"

    @classmethod
    def get_user_makepkg_path(cls) -> Optional[str]:
        if cls._user_makepkg_path == 'unset':
            possible_paths = [
                os.path.expanduser('~/.makepkg.conf'),
                os.path.join(CONFIG_ROOT, "pacman/makepkg.conf"),
            ]
            config_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    config_path = path
            cls._user_makepkg_path = config_path
        return cls._user_makepkg_path

    @classmethod
    def get(cls, key: str, fallback: Any = None, config_path: str = None) -> Any:
        value = ConfigReader.get(key, fallback, config_path="/etc/makepkg.conf")
        if cls.get_user_makepkg_path():
            print(cls.get_user_makepkg_path())
            value = ConfigReader.get(key, value, config_path=cls.get_user_makepkg_path())
        if config_path:
            value = ConfigReader.get(key, value, config_path=config_path)
        return value


class PackageBuild(DataType):
    # pylint: disable=too-many-instance-attributes
    clone = False
    pull = False

    package_base: str = None
    package_names: List[str] = None

    repo_path: str = None
    build_dir: str = None
    package_dir: str = None
    built_packages_paths: Dict[str, str] = None

    already_installed: bool = None
    failed: bool = None
    reviewed = False
    built_packages_installed: Dict[str, bool] = None

    new_deps_to_install: List[str] = None
    new_make_deps_to_install: List[str] = None
    built_deps_to_install: Dict[str, str] = None

    def __init__(self, package_names: List[str]) -> None:  # pylint: disable=super-init-not-called
        self.package_names = package_names
        self.package_base = find_aur_packages([package_names[0]])[0][0].packagebase

        self.repo_path = os.path.join(CACHE_ROOT, AUR_REPOS_CACHE_DIR,
                                      self.package_base)
        self.build_dir = os.path.join(CACHE_ROOT, BUILD_CACHE_DIR,
                                      self.package_base)
        self.package_dir = os.path.join(CACHE_ROOT, PACKAGE_CACHE_DIR)
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

    def create_clone_task_worker(self) -> CmdTaskWorker:
        return CmdTaskWorker([
            'git',
            'clone',
            get_repo_url(self.package_base),
            self.repo_path,
        ])

    def create_pull_task_worker(self) -> CmdTaskWorker:
        return CmdTaskWorker([
            'git',
            '-C',
            self.repo_path,
            'pull',
            'origin',
            'master'
        ])

    def git_reset_changed(self) -> CmdTaskResult:
        return SingleTaskExecutor(CmdTaskWorker([
            'git',
            '-C',
            self.repo_path,
            'checkout',
            '--',
            "*"
        ])).execute()

    def git_clean(self) -> CmdTaskResult:
        return SingleTaskExecutor(CmdTaskWorker([
            'git',
            '-C',
            self.repo_path,
            'clean',
            '-f',
            '-d',
            '-x'
        ])).execute()

    def create_task_worker(self) -> CmdTaskWorker:
        if self.pull:
            return self.create_pull_task_worker()
        elif self.clone:
            return self.create_clone_task_worker()
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
        self.already_installed = min([
            (
                pkg_name in PackageDB.get_local_dict().keys()
            ) and (
                self.last_installed_hash == self.current_hash
            )
            for pkg_name in self.package_names
        ])
        return self.already_installed

    @property
    def all_deps_to_install(self) -> List[str]:
        return self.new_make_deps_to_install + self.new_deps_to_install

    def _install_built_deps(
            self,
            args: PikaurArgs,
            all_package_builds: Dict[str, 'PackageBuild']
    ) -> None:

        self.built_deps_to_install = {}
        for dep in self.all_deps_to_install:
            # @TODO: check if dep is Provided by built package
            if dep not in all_package_builds:
                continue
            # @TODO: check package version?
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

        if self.built_deps_to_install:
            print('{} {}:'.format(
                color_line('::', 13),
                _("Installing already built dependencies for {}").format(
                    bold_line(', '.join(self.package_names)))
            ))
            if retry_interactive_command(
                    [
                        'sudo',
                        'pacman',
                        '--upgrade',
                        '--asdeps',
                        f'--ask={ASK_BITS}',
                    ] + reconstruct_args(args, ignore_args=[
                        'upgrade',
                        'asdeps',
                        'sync',
                        'sysupgrade',
                        'refresh',
                        'downloadonly',
                    ]) + list(self.built_deps_to_install.values()),
            ):
                for pkg_name in self.built_deps_to_install:
                    all_package_builds[pkg_name].built_packages_installed[pkg_name] = True
            else:
                self.failed = True
                raise DependencyError()

    def _set_built_package_path(self) -> None:
        dest_dir = MakepkgConfig.get('PKGDEST', self.build_dir)
        pkg_ext = MakepkgConfig.get(
            'PKGEXT', '.pkg.tar.xz',
            config_path=os.path.join(self.build_dir, 'PKGBUILD')
        )
        full_pkg_names = SingleTaskExecutor(CmdTaskWorker(
            isolate_root_cmd(['makepkg', '--packagelist'],
                             cwd=self.build_dir),
            cwd=self.build_dir
        )).execute().stdout.splitlines()
        full_pkg_names.sort(key=len)
        for pkg_name in self.package_names:
            full_pkg_name = full_pkg_names[0]
            if len(full_pkg_names) > 1:
                arch = platform.machine()
                for each_filename in full_pkg_names:
                    if pkg_name in each_filename and (
                            each_filename.endswith(arch) or
                            each_filename.endswith('-any')
                    ):
                        full_pkg_name = each_filename
                        break
            built_package_path = os.path.join(dest_dir, full_pkg_name + pkg_ext)
            if not os.path.exists(built_package_path):
                BuildError(_("{} does not exist on the filesystem.").format(built_package_path))
            if dest_dir == self.build_dir:
                new_package_path = os.path.join(self.package_dir, full_pkg_name + pkg_ext)
                if not os.path.exists(self.package_dir):
                    os.makedirs(self.package_dir)
                if os.path.exists(new_package_path):
                    os.remove(new_package_path)
                shutil.move(built_package_path, self.package_dir)
                built_package_path = new_package_path
            self.built_packages_paths[pkg_name] = built_package_path

    def build(
            self, args: PikaurArgs, all_package_builds: Dict[str, 'PackageBuild']
    ) -> None:

        if running_as_root():
            # Let systemd-run setup the directories and symlinks
            true_cmd = isolate_root_cmd(['true'])
            SingleTaskExecutor(CmdTaskWorker(true_cmd)).execute()
            # Chown the private CacheDirectory to root to signal systemd that
            # it needs to recursively chown it to the correct user
            os.chown(os.path.realpath(CACHE_ROOT), 0, 0)

        if os.path.exists(self.build_dir) and not PikaurConfig().build.get('KeepBuildDir'):
            remove_dir(self.build_dir)
        shutil.copytree(self.repo_path, self.build_dir)

        src_info = PackageBaseSrcInfo(self.repo_path)
        make_deps = [pkg_name for pkg_name, _vm in src_info.get_makedepends()]
        __, self.new_make_deps_to_install = find_local_packages(make_deps)
        new_deps = [pkg_name for pkg_name, _vm in src_info.get_depends()]
        __, self.new_deps_to_install = find_local_packages(new_deps)

        self._install_built_deps(args, all_package_builds)

        makepkg_args = []
        if not args.needed:
            makepkg_args.append('--force')

        print()
        build_succeeded = retry_interactive_command(
            isolate_root_cmd(
                [
                    'makepkg',
                    '--syncdeps',
                    '--rmdeps',
                    # f'--ask={ASK_BITS}',
                ] + (['--noconfirm'] if args.noconfirm else []) + makepkg_args,
                cwd=self.build_dir
            ),
            cwd=self.build_dir
        )

        if not build_succeeded:
            self.failed = True
            raise BuildError()
        else:
            self._set_built_package_path()


def clone_pkgbuilds_git_repos(package_names: List[str]) -> Dict[str, PackageBuild]:
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
    results = MultipleTasksExecutor({
        pkgbase: repo_status.create_task_worker()
        for pkgbase, repo_status in package_builds_by_base.items()
    }).execute()
    for package_name, result in results.items():
        if result.return_code > 0:
            raise CloneError(
                build=package_builds_by_name[package_name],
                result=result
            )
    return package_builds_by_name
