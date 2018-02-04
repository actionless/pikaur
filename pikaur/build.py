import os
import glob
import shutil

from .core import (
    DataType, CmdTaskWorker,
    MultipleTasksExecutor, SingleTaskExecutor,
    interactive_spawn, get_package_name_from_depend_line,
)
from .config import AUR_REPOS_CACHE, BUILD_CACHE
from .aur import get_repo_url
from .pacman import find_local_packages
from .args import reconstruct_args


class BuildError(Exception):
    pass


class CloneError(DataType, Exception):
    build = None
    result = None


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

    def check_installed_status(self, local_packages_found):
        already_installed = False
        last_installed_file_path = os.path.join(
            self.repo_path,
            'last_installed.txt'
        )
        if (
                self.package_name in local_packages_found
        ) and (
            os.path.exists(last_installed_file_path)
        ):
            with open(last_installed_file_path) as last_installed_file:
                last_installed_hash = last_installed_file.readlines()
                with open(
                    os.path.join(
                        self.repo_path,
                        '.git/refs/heads/master'
                    )
                ) as current_hash_file:
                    current_hash = current_hash_file.readlines()
                    if last_installed_hash == current_hash:
                        already_installed = True
        self.already_installed = already_installed
        return already_installed

    def build(self, args):

        repo_path = self.repo_path
        build_dir = os.path.join(BUILD_CACHE, self.package_name)
        if os.path.exists(build_dir):
            try:
                shutil.rmtree(build_dir)
            except PermissionError:
                interactive_spawn(['rm', '-rf', build_dir])
        shutil.copytree(repo_path, build_dir)

        make_deps = SrcInfo(repo_path).get_makedepends()
        _, new_make_deps_to_install = find_local_packages(make_deps)
        new_deps = SrcInfo(repo_path).get_depends()
        _, new_deps_to_install = find_local_packages(new_deps)
        if new_make_deps_to_install or new_deps_to_install:
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
                ]) + new_make_deps_to_install + new_deps_to_install,
            )
            if deps_result.returncode > 0:
                raise BuildError()
        build_result = interactive_spawn(
            [
                'makepkg',
                # '-rsf', '--noconfirm',
                '--nodeps',
            ],
            cwd=build_dir
        )
        if new_make_deps_to_install:
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
                interactive_spawn(
                    [
                        'sudo',
                        'pacman',
                        '-Rs',
                    ] + new_deps_to_install,
                )
            raise BuildError()
        else:
            self.built_package_path = glob.glob(
                os.path.join(build_dir, '*.pkg.tar.xz')
            )[0]


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
