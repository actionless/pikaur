import os
import shutil
import configparser
import platform

from .core import (
    DataType, CmdTaskWorker,
    MultipleTasksExecutor, SingleTaskExecutor,
    interactive_spawn, get_package_name_from_depend_line,
    ask_to_retry_decorator,
)
from .config import AUR_REPOS_CACHE, BUILD_CACHE
from .aur import get_repo_url
from .pacman import find_local_packages, PackageDB
from .args import reconstruct_args
from .pprint import color_line, bold_line


@ask_to_retry_decorator
def retry_interactive_command(cmd_args):
    good = interactive_spawn(cmd_args).returncode == 0
    if not good:
        print(color_line('Command "{}" failed to execute.'.format(
            ' '.join(cmd_args)
        ), 9))
    return good


class BuildError(Exception):
    pass


class CloneError(DataType, Exception):
    build = None
    result = None


class DependencyError(Exception):
    pass


class SrcInfo():

    lines = None
    path = None
    repo_path = None

    def __init__(self, repo_path):
        self.path = os.path.join(
            repo_path,
            '.SRCINFO'
        )
        self.repo_path = repo_path
        with open(self.path) as srcinfo_file:
            self.lines = srcinfo_file.readlines()

    def get_values(self, field):
        prefix = field + ' = '
        values = []
        for line in self.lines:
            if line.strip().startswith(prefix):
                values.append(line.strip().split(prefix)[1])
        return values

    def get_install_script(self):
        values = self.get_values('install')
        if values:
            return values[0]
        return None

    def _get_depends(self, field):
        return [
            get_package_name_from_depend_line(dep)
            for dep in self.get_values(field)
        ]

    def get_makedepends(self):
        return self._get_depends('makedepends')

    def get_depends(self):
        return self._get_depends('depends')

    def regenerate(self):
        with open(self.path, 'w') as srcinfo_file:
            result = SingleTaskExecutor(
                CmdTaskWorker([
                    'makepkg', '--printsrcinfo',
                ], cwd=self.repo_path)
            ).execute()
            srcinfo_file.write(result.stdout)


class MakepkgConfig():

    _cached_config = None

    @classmethod
    def get_config(cls):
        if not cls._cached_config:
            config = configparser.ConfigParser(allow_no_value=True)
            with open('/etc/makepkg.conf') as config_file:
                config_string = '[all]\n' + config_file.read()
            config.read_string(config_string)
            cls._cached_config = config['all']
        return cls._cached_config

    @classmethod
    def get(cls, key, fallback=None):
        value = cls.get_config().get(key, fallback)
        if value:
            value = value.strip('"').strip("'")
        return value


class PackageBuild(DataType):
    clone = False
    pull = False

    package_name = None

    repo_path = None
    built_package_path = None

    already_installed = None

    def __init__(self, package_name):  # pylint: disable=super-init-not-called
        self.package_name = package_name
        repo_path = os.path.join(AUR_REPOS_CACHE, package_name)
        if os.path.exists(repo_path):
            # pylint: disable=simplifiable-if-statement
            if os.path.exists(os.path.join(repo_path, '.git')):
                self.pull = True
            else:
                self.clone = True
        else:
            os.makedirs(repo_path)
            self.clone = True
        self.repo_path = repo_path

    def create_clone_task(self):
        return CmdTaskWorker([
            'git',
            'clone',
            get_repo_url(self.package_name),
            self.repo_path,
        ])

    def create_pull_task(self):
        return CmdTaskWorker([
            'git',
            '-C',
            self.repo_path,
            'pull',
            'origin',
            'master'
        ])

    def create_task(self):
        if self.pull:
            return self.create_pull_task()
        elif self.clone:
            return self.create_clone_task()
        return NotImplemented

    @property
    def last_installed_file_path(self):
        return os.path.join(
            self.repo_path,
            'last_installed.txt'
        )

    @property
    def is_installed(self):
        return os.path.exists(self.last_installed_file_path)

    @property
    def last_installed_hash(self):
        if self.is_installed:
            with open(self.last_installed_file_path) as last_installed_file:
                return last_installed_file.readlines()[0].strip()
        return None

    def update_last_installed_file(self):
        shutil.copy2(
            os.path.join(
                self.repo_path,
                '.git/refs/heads/master'
            ),
            self.last_installed_file_path
        )

    @property
    def build_files_updated(self):
        if (
                self.is_installed
        ) and (
            self.last_installed_hash != self.current_hash
        ):
            return True
        return False

    @property
    def current_hash(self):
        with open(
            os.path.join(
                self.repo_path,
                '.git/refs/heads/master'
            )
        ) as current_hash_file:
            return current_hash_file.readlines()[0].strip()

    @property
    def version_already_installed(self):
        already_installed = False
        if (
                self.package_name in PackageDB.get_local_dict().keys()
        ) and (
            self.last_installed_hash == self.current_hash
        ):
            already_installed = True
        self.already_installed = already_installed
        return already_installed

    def build(self, args, all_package_builds):
        # @TODO: split into smaller routines
        repo_path = self.repo_path
        build_dir = os.path.join(BUILD_CACHE, self.package_name)
        if os.path.exists(build_dir):
            try:
                shutil.rmtree(build_dir)
            except PermissionError:
                interactive_spawn(['sudo', 'rm', '-rf', build_dir])
        shutil.copytree(repo_path, build_dir)

        src_info = SrcInfo(repo_path)
        make_deps = src_info.get_makedepends()
        _, new_make_deps_to_install = find_local_packages(make_deps)
        new_deps = src_info.get_depends()
        _, new_deps_to_install = find_local_packages(new_deps)
        all_deps_to_install = new_make_deps_to_install + new_deps_to_install

        built_deps_to_install = []
        for dep in all_deps_to_install[:]:
            if dep in all_package_builds:
                built_deps_to_install.append(
                    all_package_builds[dep].built_package_path
                )
                all_deps_to_install.remove(dep)

        if built_deps_to_install:
            print('{} {} {}:'.format(
                color_line('::', 13),
                "Installing already built dependencies for",
                bold_line(self.package_name)
            ))
            if not retry_interactive_command(
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
                    ]) + built_deps_to_install,
            ):
                raise DependencyError()

        if all_deps_to_install:
            local_provided = PackageDB.get_local_provided()
            for dep_name in all_deps_to_install[:]:
                if dep_name in local_provided:
                    all_deps_to_install.remove(dep_name)
        if all_deps_to_install:
            print('{} {} {}:'.format(
                color_line('::', 13),
                "Installing repository dependencies for",
                bold_line(self.package_name)
            ))
            deps_result = interactive_spawn(
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
                ]) + all_deps_to_install,
            )
            if deps_result.returncode > 0:
                raise BuildError()
        makepkg_args = [
            '--nodeps',
        ]

        if not args.needed:
            makepkg_args.append('--force')
        build_result = interactive_spawn(
            [
                'makepkg',
            ] + makepkg_args,
            cwd=build_dir
        )

        if new_make_deps_to_install:
            print('{} {} {}:'.format(
                color_line('::', 13),
                "Removing make dependencies for",
                bold_line(self.package_name)
            ))
            # @TODO: resolve makedeps in case if it was specified by Provides, not real name
            interactive_spawn(
                [
                    'sudo',
                    'pacman',
                    '-Rs',
                    '--noconfirm',
                ] + new_make_deps_to_install,
            )

        if build_result.returncode > 0:
            if new_deps_to_install:
                print('{} {} {}:'.format(
                    color_line('::', 13),
                    "Removing already installed dependencies for",
                    bold_line(self.package_name)
                ))
                interactive_spawn(
                    [
                        'sudo',
                        'pacman',
                        '-Rs',
                    ] + new_deps_to_install,
                )
            raise BuildError()
        else:
            pkg_ext = MakepkgConfig.get('PKGEXT', '.pkg.tar.xz')
            dest_dir = MakepkgConfig.get('PKGDEST', build_dir)
            full_pkg_names = SingleTaskExecutor(CmdTaskWorker(
                ['makepkg', '--packagelist', ],
                cwd=build_dir
            )).execute().stdout.splitlines()
            full_pkg_name = full_pkg_names[0]
            if len(full_pkg_names) > 1:
                arch = platform.machine()
                for pkg_name in full_pkg_names:
                    if arch in pkg_name:
                        full_pkg_name = pkg_name
            self.built_package_path = os.path.join(dest_dir, full_pkg_name+pkg_ext)


def clone_pkgbuilds_git_repos(package_names):
    package_builds = {
        package_name: PackageBuild(package_name)
        for package_name in package_names
    }
    results = MultipleTasksExecutor({
        repo_status.package_name: repo_status.create_task()
        for repo_status in package_builds.values()
    }).execute()
    for package_name, result in results.items():
        if result.return_code > 0:
            raise CloneError(
                build=package_builds[package_name],
                result=result
            )
    return package_builds
