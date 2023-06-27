import os
from pathlib import Path
from typing import TYPE_CHECKING

from .args import parse_args
from .aur import AURPackageInfo, find_aur_packages, get_repo_url
from .aur_deps import get_aur_deps_list
from .core import check_runtime_deps, interactive_spawn
from .exceptions import PackagesNotFoundInRepoError
from .i18n import translate
from .pacman import PackageDB
from .pprint import print_stdout
from .print_department import print_not_found_packages
from .urllib import wrap_proxy_env

if TYPE_CHECKING:
    import pyalpm


def clone_aur_pkgs(aur_pkgs: list[AURPackageInfo], pwd: Path) -> None:
    for aur_pkg in aur_pkgs:
        name = aur_pkg.name
        repo_path = pwd / name
        print_stdout()
        action = "clone"
        if repo_path.exists():
            action = "update"
        if action == "clone":
            interactive_spawn(
                wrap_proxy_env([
                    "git",
                    "clone",
                    get_repo_url(aur_pkg.packagebase),
                    str(repo_path),
                ]),
            )
        elif action == "update":
            interactive_spawn([
                "git",
                "-C", repo_path.as_posix(),
                "pull",
                "origin",
                "master",
            ])
        else:
            raise NotImplementedError


def clone_repo_pkgs(repo_pkgs: list["pyalpm.Package"], pwd: Path) -> None:
    for repo_pkg in repo_pkgs:
        name = repo_pkg.name
        repo_path = pwd / name
        action = "clone"
        if repo_path.exists():
            action = "update"
        print_stdout()
        print_stdout(translate(f"Package '{name}' going to be cloned into '{repo_path}'..."))
        if action == "clone":
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
        elif action == "update":
            interactive_spawn([
                "git",
                "-C", repo_path.as_posix(),
                "pull",
                "origin",
                "main",
            ])
        else:
            raise NotImplementedError


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
        check_runtime_deps(["pkgctl"])

    if not_found_repo_pkgs:
        print_not_found_packages(not_found_repo_pkgs)

    if args.deps:
        aur_pkgs = aur_pkgs + get_aur_deps_list(aur_pkgs)

    clone_aur_pkgs(aur_pkgs=aur_pkgs, pwd=pwd)
    clone_repo_pkgs(repo_pkgs=repo_pkgs, pwd=pwd)
