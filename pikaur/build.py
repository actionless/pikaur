import os
import shutil
import platform
from typing import List, Union, Dict

from .core import (
    DataType, CmdTaskWorker, CmdTaskResult,
    MultipleTasksExecutor, SingleTaskExecutor,
    ConfigReader, isolate_root_cmd, remove_dir, running_as_root,
)
from .i18n import _
from .version import get_package_name_and_version_matcher_from_depend_line
from .config import (
    CACHE_ROOT, AUR_REPOS_CACHE_DIR, BUILD_CACHE_DIR, PACKAGE_CACHE_DIR,
)
from .aur import get_repo_url
from .pacman import find_local_packages, PackageDB
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

    def __init__(self, repo_path: str, package_name: str) -> None:
        self.path = os.path.join(
            repo_path,
            '.SRCINFO'
        )
        self.repo_path = repo_path

        self._common_lines = []
        self._package_lines = []
        destination = self._common_lines
        with open(self.path) as srcinfo_file:
            for line in srcinfo_file.readlines():
                if line.startswith('pkgname ='):
                    if line.split('=')[1].strip() == package_name:
                        destination = self._package_lines
                    else:
                        destination = []
                else:
                    destination.append(line)

    def get_values(self, field: str) -> List[str]:
        prefix = field + ' = '
        values = []
        for lines in (self._common_lines, self._package_lines):
            for line in lines:
                if line.strip().startswith(prefix):
                    values.append(line.strip().split(prefix)[1])
        return values

    def get_install_script(self) -> str:
        values = self.get_values('install')
        if values:
            return values[0]
        return None

    def _get_depends(self, field: str) -> List[str]:
        return [
            get_package_name_and_version_matcher_from_depend_line(dep)[0]
            for dep in self.get_values(field)
        ]

    def get_makedepends(self) -> List[str]:
        return self._get_depends('makedepends')

    def get_depends(self) -> List[str]:
        return self._get_depends('depends')

    def regenerate(self) -> None:
        with open(self.path, 'w') as srcinfo_file:
            result = SingleTaskExecutor(
                CmdTaskWorker(isolate_root_cmd(['makepkg', '--printsrcinfo'],
                                               cwd=self.repo_path),
                              cwd=self.repo_path)
            ).execute()
            srcinfo_file.write(result.stdout)


class MakepkgConfig(ConfigReader):
    default_config_path: str = "/etc/makepkg.conf"  # type: ignore


class PackageBuild(DataType):
    # pylint: disable=too-many-instance-attributes
    clone = False
    pull = False

    package_name: str = None

    repo_path: str = None
    build_dir: str = None
    package_dir: str = None
    built_package_path: str = None

    already_installed: bool = None
    failed: bool = None
    built_package_installed = False

    new_deps_to_install: List[str] = None
    new_make_deps_to_install: List[str] = None
    built_deps_to_install: Dict[str, str] = None

    def __init__(self, package_name: str) -> None:  # pylint: disable=super-init-not-called
        self.package_name = package_name

        self.repo_path = os.path.join(CACHE_ROOT, AUR_REPOS_CACHE_DIR,
                                      self.package_name)
        self.build_dir = os.path.join(CACHE_ROOT, BUILD_CACHE_DIR,
                                      self.package_name)
        self.package_dir = os.path.join(CACHE_ROOT, PACKAGE_CACHE_DIR)

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
            get_repo_url(self.package_name),
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
            with open(self.last_installed_file_path) as last_installed_file:
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
        with open(
            os.path.join(
                self.repo_path,
                '.git/refs/heads/master'
            )
        ) as current_hash_file:
            return current_hash_file.readlines()[0].strip()

    @property
    def version_already_installed(self) -> bool:
        already_installed = False
        if (
                self.package_name in PackageDB.get_local_dict().keys()
        ) and (
            self.last_installed_hash == self.current_hash
        ):
            already_installed = True
        self.already_installed = already_installed
        return already_installed

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
            package_build = all_package_builds[dep]
            if package_build.failed:
                self.failed = True
                raise DependencyError()
            if not package_build.built_package_path:
                raise DependencyNotBuiltYet()
            if not package_build.built_package_installed:
                self.built_deps_to_install[
                    package_build.package_name
                ] = package_build.built_package_path
            if dep in self.new_make_deps_to_install:
                self.new_make_deps_to_install.remove(dep)
            if dep in self.new_deps_to_install:
                self.new_deps_to_install.remove(dep)

        if self.built_deps_to_install:
            print('{} {}:'.format(
                color_line('::', 13),
                _("Installing already built dependencies for {}").format(
                    bold_line(self.package_name))
            ))
            if retry_interactive_command(
                    [
                        'sudo',
                        'pacman',
                        '--upgrade',
                        '--asdeps',
                        '--noconfirm',
                    ] + reconstruct_args(args, ignore_args=[
                        'upgrade',
                        'asdeps',
                        'noconfirm',
                        'sync',
                        'sysupgrade',
                        'refresh',
                        'downloadonly',
                    ]) + list(self.built_deps_to_install.values()),
            ):
                for pkg_name in self.built_deps_to_install:
                    all_package_builds[pkg_name].built_package_installed = True
            else:
                self.failed = True
                raise DependencyError()

    def _install_repo_deps(self, args: PikaurArgs) -> None:

        if self.all_deps_to_install:
            local_provided = PackageDB.get_local_provided_names()
            for dep_name in self.all_deps_to_install:
                if dep_name in local_provided:
                    if dep_name in self.new_make_deps_to_install:
                        self.new_make_deps_to_install.remove(dep_name)
                    if dep_name in self.new_deps_to_install:
                        self.new_deps_to_install.remove(dep_name)
        if self.all_deps_to_install:
            all_repo_pkgs_names = PackageDB.get_repo_dict().keys()
            for pkg_name in self.all_deps_to_install:
                if (
                        pkg_name not in all_repo_pkgs_names
                ) and (
                    pkg_name in self.new_make_deps_to_install
                ):
                    # @TODO: choose alternative provided packages?
                    provided_by = PackageDB.get_repo_provided_dict()[pkg_name][0].name
                    #
                    self.new_make_deps_to_install.remove(pkg_name)
                    self.new_make_deps_to_install.append(provided_by)
            print('{} {}:'.format(
                color_line('::', 13),
                _("Installing repository dependencies for {}").format(
                    bold_line(self.package_name))
            ))
            if not retry_interactive_command(
                    [
                        'sudo',
                        'pacman',
                        '--sync',
                        '--asdeps',
                        '--needed',
                        '--noconfirm',
                    ] + reconstruct_args(args, ignore_args=[
                        'sync',
                        'asdeps',
                        'needed',
                        'noconfirm',
                        'sysupgrade',
                        'refresh',
                    ]) + self.all_deps_to_install,
            ):
                self.failed = True
                raise BuildError()

    def _remove_deps(self) -> None:
        if self.new_deps_to_install or self.built_deps_to_install:
            print('{} {}:'.format(
                color_line('::', 13),
                _("Removing already installed dependencies for {}").format(
                    bold_line(self.package_name))
            ))
            retry_interactive_command(
                [
                    'sudo',
                    'pacman',
                    '-Rs',
                    '--noconfirm',
                ] + self.new_deps_to_install + list(self.built_deps_to_install),
            )

    def _remove_make_deps(self) -> None:
        if self.new_make_deps_to_install:
            print('{} {}:'.format(
                color_line('::', 13),
                _("Removing make dependencies for {}").format(
                    bold_line(self.package_name))
            ))
            retry_interactive_command(
                [
                    'sudo',
                    'pacman',
                    '-Rs',
                    '--noconfirm',
                ] + self.new_make_deps_to_install,
            )

    def _set_built_package_path(self) -> None:
        dest_dir = MakepkgConfig.get('PKGDEST', self.build_dir)
        pkg_ext = MakepkgConfig.get('PKGEXT', '.pkg.tar.xz')
        pkg_ext = MakepkgConfig.get(
            'PKGEXT', pkg_ext,
            config_path=os.path.join(self.build_dir, 'PKGBUILD')
        )
        full_pkg_names = SingleTaskExecutor(CmdTaskWorker(
            isolate_root_cmd(['makepkg', '--packagelist'],
                             cwd=self.build_dir),
            cwd=self.build_dir
        )).execute().stdout.splitlines()
        full_pkg_name = full_pkg_names[0]
        if len(full_pkg_names) > 1:
            arch = platform.machine()
            for pkg_name in full_pkg_names:
                if arch in pkg_name and self.package_name in pkg_name:
                    full_pkg_name = pkg_name
        built_package_path = os.path.join(dest_dir, full_pkg_name+pkg_ext)
        if not os.path.exists(built_package_path):
            return
        if dest_dir == self.build_dir:
            new_package_path = os.path.join(self.package_dir, full_pkg_name+pkg_ext)
            if not os.path.exists(self.package_dir):
                os.makedirs(self.package_dir)
            if os.path.exists(new_package_path):
                os.remove(new_package_path)
            shutil.move(built_package_path, self.package_dir)
            built_package_path = new_package_path
        self.built_package_path = built_package_path

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

        if os.path.exists(self.build_dir):
            remove_dir(self.build_dir)
        shutil.copytree(self.repo_path, self.build_dir)

        src_info = SrcInfo(self.repo_path, self.package_name)
        make_deps = src_info.get_makedepends()
        __, self.new_make_deps_to_install = find_local_packages(make_deps)
        new_deps = src_info.get_depends()
        __, self.new_deps_to_install = find_local_packages(new_deps)

        self._install_built_deps(args, all_package_builds)
        self._install_repo_deps(args)

        makepkg_args = [
            '--nodeps', '--noconfirm',
        ]
        if not args.needed:
            makepkg_args.append('--force')

        print()
        build_succeeded = retry_interactive_command(
            isolate_root_cmd(
                ['makepkg'] + makepkg_args,
                cwd=self.build_dir
            ),
            cwd=self.build_dir
        )

        self._remove_make_deps()
        if args.downloadonly:
            self._remove_deps()

        if not build_succeeded:
            self._remove_deps()
            self.failed = True
            raise BuildError()
        else:
            self._set_built_package_path()


def clone_pkgbuilds_git_repos(package_names: List[str]) -> Dict[str, PackageBuild]:
    package_builds = {
        package_name: PackageBuild(package_name)
        for package_name in package_names
    }
    results = MultipleTasksExecutor({
        repo_status.package_name: repo_status.create_task_worker()
        for repo_status in package_builds.values()
    }).execute()
    for package_name, result in results.items():
        if result.return_code > 0:
            raise CloneError(
                build=package_builds[package_name],
                result=result
            )
    return package_builds
