import os

from .core import CmdTaskWorker, AUR_REPOS_CACHE, TypeContainer
from .aur import get_repo_url


class SrcInfo():

    lines = None

    def __init__(self, repo_path):
        with open(
            os.path.join(
                repo_path,
                '.SRCINFO'
            )
        ) as srcinfo_file:
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

    def get_makedepends(self):
        return self.get_values('makedepends')


class PackageBuild(TypeContainer):
    clone = False
    pull = False

    package_name = None

    repo_path = None
    built_package_path = None

    already_installed = None

    def __init__(self, package_name):
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
