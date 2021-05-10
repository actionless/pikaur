import os

from .args import parse_args
from .aur_deps import get_aur_deps_list
from .aur import find_aur_packages, get_repo_url
from .core import check_runtime_deps, interactive_spawn
from .i18n import _
from .pacman import PackageDB, PackagesNotFoundInRepo
from .pprint import print_stdout
from .print_department import print_not_found_packages
from .urllib import wrap_proxy_env


def cli_getpkgbuild() -> None:
    args = parse_args()
    pwd = os.path.abspath(os.path.curdir)
    aur_pkg_names = args.positional

    aur_pkgs, not_found_aur_pkgs = find_aur_packages(aur_pkg_names)
    repo_pkgs = []
    not_found_repo_pkgs = []
    for pkg_name in not_found_aur_pkgs:
        try:
            repo_pkg = PackageDB.find_repo_package(pkg_name)
        except PackagesNotFoundInRepo:
            not_found_repo_pkgs.append(pkg_name)
        else:
            repo_pkgs.append(repo_pkg)

    if repo_pkgs:
        check_runtime_deps(['asp'])

    if not_found_repo_pkgs:
        print_not_found_packages(not_found_repo_pkgs)

    if args.deps:
        aur_pkgs = aur_pkgs + get_aur_deps_list(aur_pkgs)

    for aur_pkg in aur_pkgs:
        name = aur_pkg.name
        repo_path = os.path.join(pwd, name)
        print_stdout()
        interactive_spawn(wrap_proxy_env([
            'git',
            'clone',
            get_repo_url(aur_pkg.packagebase),
            repo_path,
        ]))

    for repo_pkg in repo_pkgs:
        name = repo_pkg.name
        repo_path = os.path.join(pwd, name)
        action = 'checkout'
        if os.path.exists(repo_path):
            action = 'update'
        print_stdout()
        print_stdout(_(f"Package '{name}' going to be cloned into '{repo_path}'..."))
        interactive_spawn([
            'asp',
            action,
            name,
        ])
