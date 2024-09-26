"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

from datetime import datetime
from typing import TYPE_CHECKING

from .alpm import PacmanConfig
from .args import parse_args
from .aur import find_aur_packages
from .config import DEFAULT_TIMEZONE, PikaurConfig
from .exceptions import PackagesNotFoundInRepoError
from .i18n import translate, translate_many
from .pacman import (
    PackageDB,
    find_packages_not_from_repo,
    find_upgradeable_packages,
    get_ignored_pkgnames_from_patterns,
)
from .pikaprint import print_stderr, print_stdout
from .pikatypes import AURInstallInfo, InstallInfo, RepoInstallInfo
from .print_department import (
    pretty_format_upgradeable,
    print_ignored_package,
    print_ignoring_outofdate_upgrade,
    print_stable_version_upgrades,
)
from .version import VERSION_DEVEL, compare_versions

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Final

    import pyalpm

    from .pikatypes import AURPackageInfo


DEVEL_PKGS_POSTFIXES: "Final" = (
    "-git",
    "-svn",
    "-bzr",
    "-hg",
    "-cvs",
    "-nightly",
)


def devel_pkgname_to_stable(pkg_name: str) -> str | None:
    result = None
    for devel_pkg_postfix in DEVEL_PKGS_POSTFIXES:
        if pkg_name.endswith(devel_pkg_postfix):
            result = pkg_name[:-len(devel_pkg_postfix)]
            break
    return result


def is_devel_pkg(pkg_name: str) -> bool:
    return bool(devel_pkgname_to_stable(pkg_name))


def convert_devel_pgnames_to_stable(pkgs: list[str]) -> dict[str, str]:
    return {
        stable_name: pkg
        for pkg in pkgs
        if (stable_name := devel_pkgname_to_stable(pkg))
    }


def get_remote_package(
        new_pkg_name: str,
) -> "pyalpm.Package | AURPackageInfo | None":
    try:
        repo_pkg = PackageDB.find_repo_package(new_pkg_name)
    except PackagesNotFoundInRepoError:
        aur_packages, _not_found = find_aur_packages([new_pkg_name])
        if aur_packages:
            return aur_packages[0]
        return None
    return repo_pkg


def get_remote_package_version(new_pkg_name: str) -> str | None:
    pkg = get_remote_package(new_pkg_name)
    if pkg:
        return pkg.version
    return None


def find_repo_upgradeable() -> list[RepoInstallInfo]:
    """
    Unlike `pikaur.install_info_fetcher.InstallInfoFetcher.get_upgradeable_repo_pkgs_info`
    it find all upgradeable repo packages, even ignored ones or conflicting
    (like `pacman -Qu`).
    """
    all_local_pkgs = PackageDB.get_local_dict()
    repo_packages_updates = []
    for repo_pkg in find_upgradeable_packages():
        local_pkg = all_local_pkgs[repo_pkg.name]
        repo_packages_updates.append(
            RepoInstallInfo(
                package=repo_pkg,
                current_version=local_pkg.version,
            ),
        )
    return repo_packages_updates


def find_aur_devel_updates(
        aur_pkgs_info: "list[AURPackageInfo]",
        package_ttl_days: int,
) -> list[AURInstallInfo]:
    local_packages = PackageDB.get_local_dict()
    now = datetime.now(tz=DEFAULT_TIMEZONE)
    aur_updates = []
    for aur_pkg in sorted(aur_pkgs_info, key=lambda x: x.name):
        pkg_name = aur_pkg.name
        if not is_devel_pkg(pkg_name):
            continue
        local_pkg = local_packages[pkg_name]
        pkg_install_datetime = datetime.fromtimestamp(
            local_pkg.installdate, tz=DEFAULT_TIMEZONE,
        )
        pkg_age_days = (now - pkg_install_datetime).days
        if pkg_age_days >= package_ttl_days:
            aur_updates.append(AURInstallInfo(
                package=aur_pkg,
                current_version=local_pkg.version,
                new_version=VERSION_DEVEL,
                devel_pkg_age_days=pkg_age_days,
            ))
    return aur_updates


def find_aur_updates(  # pylint: disable=too-many-branches
        *, check_stable_versions_of_devel_pkgs: bool = False,
) -> tuple[list[AURInstallInfo], list[str], dict[str, InstallInfo]]:
    args = parse_args()
    local_packages = PackageDB.get_local_dict()
    package_names = find_packages_not_from_repo()
    print_stderr(translate_many(
        "Reading AUR package info...",
        "Reading AUR packages info...",
        len(package_names),
    ))

    stable_to_devel_names = {}
    if check_stable_versions_of_devel_pkgs:
        local_pkg_names = PackageDB.get_local_pkgnames()
        stable_to_devel_names = convert_devel_pgnames_to_stable(
            local_pkg_names,
        )
    stable_names_of_devel_pkgs = list(stable_to_devel_names.keys())

    aur_pkgs_info, not_found_aur_pkgs = find_aur_packages(
        package_names + stable_names_of_devel_pkgs,
    )

    stable_versions_pkgs: dict[str, pyalpm.Package | AURPackageInfo] = {}
    repo_pkg_names = PackageDB.get_repo_pkgnames()
    for pkg_name in stable_names_of_devel_pkgs:
        if pkg_name in not_found_aur_pkgs:
            not_found_aur_pkgs.remove(pkg_name)
            if pkg_name in repo_pkg_names:
                og_name = stable_to_devel_names[pkg_name]
                # @TODO: replace to get_repo_package():
                stable_versions_pkgs[og_name] = PackageDB.find_repo_package(pkg_name)

    aur_updates = []
    stable_versions_updates = {}
    aur_pkgs_up_to_date = []
    for aur_pkg in aur_pkgs_info:
        pkg_name = aur_pkg.name
        aur_version = aur_pkg.version
        if pkg_name in stable_names_of_devel_pkgs:
            og_name = stable_to_devel_names[pkg_name]
            stable_versions_pkgs[og_name] = aur_pkg
        else:
            current_version = local_packages[pkg_name].version
            compare_aur_pkg = compare_versions(current_version, aur_version)
            if compare_aur_pkg < 0:
                pkg_install_info = AURInstallInfo(
                    package=aur_pkg,
                    current_version=current_version,
                )
                if args.ignore_outofdate and aur_pkg.outofdate:
                    print_ignoring_outofdate_upgrade(pkg_install_info)
                    continue
                aur_updates.append(pkg_install_info)
            else:
                aur_pkgs_up_to_date.append(aur_pkg)

    for og_name, pkg in stable_versions_pkgs.items():
        current_version = local_packages[og_name].version
        compare_pkg = compare_versions(current_version, pkg.version)
        if compare_pkg < 0:
            stable_versions_updates[og_name] = InstallInfo(
                package=pkg,
                current_version=current_version,
            )

    if aur_pkgs_up_to_date:
        sync_config = PikaurConfig().sync
        devel_packages_expiration = sync_config.DevelPkgsExpiration.get_int()
        if args.devel:
            devel_packages_expiration = 0
        if devel_packages_expiration > -1:
            aur_updates += find_aur_devel_updates(
                aur_pkgs_up_to_date,
                package_ttl_days=devel_packages_expiration,
            )
    return aur_updates, not_found_aur_pkgs, stable_versions_updates


def print_upgradeable(
        aur_install_infos: "Sequence[InstallInfo] | None" = None,
        stable_versions_updates: dict[str, InstallInfo] | None = None,
        *,
        ignored_only: bool = False,
) -> None:
    args = parse_args()
    updates: list[InstallInfo] = []
    if aur_install_infos is not None:
        updates += aur_install_infos
    elif not args.repo:
        aur_updates, _not_found_aur_pkgs, stable_versions_updates = find_aur_updates()
        updates += aur_updates
    if not args.aur:
        updates += find_repo_upgradeable()
    if stable_versions_updates:
        print_stable_version_upgrades(stable_versions_updates)
    if not updates:
        return
    pkg_names = [pkg.name for pkg in updates]
    manually_ignored_pkg_names = get_ignored_pkgnames_from_patterns(
        pkg_names,
        args.ignore,
    )
    config_ignored_pkg_names = get_ignored_pkgnames_from_patterns(
        pkg_names,
        PacmanConfig().options.get("IgnorePkg", []),
    )
    ignored_pkg_names = manually_ignored_pkg_names + config_ignored_pkg_names
    for pkg in updates[:]:
        if pkg.name in ignored_pkg_names:
            updates.remove(pkg)
            ignored_from = None
            if pkg.name in config_ignored_pkg_names:
                ignored_from = translate("(ignored in Pacman config)")
            print_ignored_package(install_info=pkg, ignored_from=ignored_from)
    if ignored_only:
        return
    if args.quiet:
        print_stdout("\n".join([
            pkg_update.name for pkg_update in updates
        ]))
    else:
        print_stdout(pretty_format_upgradeable(
            updates,
            print_repo=PikaurConfig().sync.AlwaysShowPkgOrigin.get_bool(),
        ))
