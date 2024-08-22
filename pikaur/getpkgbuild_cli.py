import os
from pathlib import Path
from typing import TYPE_CHECKING

from .args import parse_args
from .aur import find_aur_packages, get_repo_url
from .aur_deps import get_aur_deps_list
from .exceptions import PackagesNotFoundInRepoError
from .i18n import translate
from .os_utils import check_executables
from .pacman import PackageDB
from .pikaprint import print_stdout
from .pikatypes import AURPackageInfo
from .print_department import print_not_found_packages
from .spawn import interactive_spawn
from .urllib_helper import wrap_proxy_env

if TYPE_CHECKING:
    import pyalpm


def clone_aur_pkgs(aur_pkgs: list[AURPackageInfo], pwd: Path) -> None:
    for aur_pkg in aur_pkgs:
        name = aur_pkg.name
        repo_path = pwd / name
        print_stdout()
        if repo_path.exists():
            interactive_spawn([
                "git",
                "-C", repo_path.as_posix(),
                "pull",
                "origin",
                "master",
            ])
        else:
            interactive_spawn(
                wrap_proxy_env([
                    "git",
                    "clone",
                    get_repo_url(aur_pkg.packagebase),
                    str(repo_path),
                ]),
            )


def clone_repo_pkgs(repo_pkgs: list["pyalpm.Package"], pwd: Path) -> None:
    for repo_pkg in repo_pkgs:
        name = repo_pkg.base
        repo_path = pwd / name
        print_stdout()
        print_stdout(translate(f"Package '{name}' going to be cloned into '{repo_path}'..."))
        if repo_path.exists():
            interactive_spawn([
                "git",
                "-C", repo_path.as_posix(),
                "pull",
                "origin",
                "main",
            ])
        else:
            interactive_spawn(
                [
                    "pkgctl",
                    "repo",
                    "clone",
                    "--protocol=https",
                    name,
                ],
                cwd=pwd,
            )


def cli_getpkgbuild() -> None:
    args = parse_args()
    pwd = Path(args.output_dir or os.path.curdir).resolve()
    aur_pkg_names = args.positional

    aur_pkgs, not_found_aur_pkgs = find_aur_packages(aur_pkg_names)
    repo_pkgs = []
    not_found_repo_pkgs = []
    for pkg_name in not_found_aur_pkgs:
        try:
            repo_pkg = PackageDB.find_repo_package(pkg_name)
        except PackagesNotFoundInRepoError:
            not_found_repo_pkgs.append(pkg_name)
        else:
            repo_pkgs.append(repo_pkg)

    if repo_pkgs:
        check_executables(["pkgctl"])

    if not_found_repo_pkgs:
        print_not_found_packages(not_found_repo_pkgs)

    if args.deps:
        aur_pkgs += get_aur_deps_list(aur_pkgs)

    clone_aur_pkgs(aur_pkgs=aur_pkgs, pwd=pwd)
    clone_repo_pkgs(repo_pkgs=repo_pkgs, pwd=pwd)
