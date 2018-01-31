from .core import (
    CmdTaskWorker, SingleTaskExecutor, PackageUpdate
)


class PacmanTaskWorker(CmdTaskWorker):

    def __init__(self, args):
        super().__init__(
            [
                "pacman",
            ] + args
        )


class PacmanColorTaskWorker(PacmanTaskWorker):

    def __init__(self, args):
        super().__init__(
            [
                "--color=always",
            ] + args
        )


def find_pacman_packages(packages, local=False):
    result = SingleTaskExecutor(
        PacmanTaskWorker(['-Ssq', ] if not local else ['-Qsq', ])
    ).execute()
    all_repo_packages = result.stdout.splitlines()
    pacman_packages = []
    not_found_packages = []
    for package_name in packages:
        if package_name not in all_repo_packages:
            not_found_packages.append(package_name)
        else:
            pacman_packages.append(package_name)
    return pacman_packages, not_found_packages


def find_repo_packages(packages):
    return find_pacman_packages(packages, local=False)


def find_local_packages(packages):
    return find_pacman_packages(packages, local=True)


def find_packages_not_from_repo():
    local_prefix = 'local/'
    result = SingleTaskExecutor(
        PacmanTaskWorker(['-Qs', ])
    ).execute()
    all_local_packages_versions = {}
    for line in result.stdout.splitlines():
        if line.startswith(local_prefix):
            pkg_name, version = line.split()[:2]
            pkg_name = pkg_name.split(local_prefix)[1]
            all_local_packages_versions[pkg_name] = version

    _repo_packages, not_found_packages = find_repo_packages(
        all_local_packages_versions.keys()
    )
    not_found_packages_versions = {
        pkg_name: all_local_packages_versions[pkg_name]
        for pkg_name in not_found_packages
    }
    return not_found_packages_versions


def find_repo_updates():
    result = SingleTaskExecutor(
        PacmanTaskWorker(['-Qu', ])
    ).execute()
    packages_updates_lines = result.stdout.splitlines()
    repo_packages_updates = []
    for update in packages_updates_lines:
        pkg_name, current_version, _, new_version, *_ = update.split()
        repo_packages_updates.append(
            PackageUpdate(
                pkg_name=pkg_name,
                aur_version=new_version,
                current_version=current_version,
            )
        )
    return repo_packages_updates
