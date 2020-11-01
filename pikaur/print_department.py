""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import sys
from datetime import datetime
from typing import TYPE_CHECKING, List, Tuple, Iterable, Union, Dict, Optional

import pyalpm

from .i18n import _, _n
from .pprint import (
    print_stderr, color_line, bold_line, format_paragraph, get_term_width,
    print_warning,
)
from .args import parse_args
from .core import PackageSource, InstallInfo
from .config import VERSION, PikaurConfig
from .version import get_common_version, get_version_diff
from .pacman import PackageDB, OFFICIAL_REPOS
from .aur import AURPackageInfo


if TYPE_CHECKING:
    # pylint: disable=unused-import,cyclic-import
    from .install_info_fetcher import InstallInfoFetcher  # noqa


GROUP_COLOR = 4
REPLACEMENTS_COLOR = 14


AnyPackage = Union[AURPackageInfo, pyalpm.Package]


def print_version(pacman_version: str, pyalpm_version: str, quiet=False) -> None:
    if quiet:
        print(f'Pikaur v{VERSION}')
        print(f'{pacman_version} - pyalpm v{pyalpm_version}')
    else:
        sys.stdout.write(r"""
      /:}               _
     /--1             / :}
    /   |           / `-/
   |  ,  --------  /   /     Pikaur v""" + VERSION + r"""
   |'                 Y      (C) 2018-2020 Pikaur development team
  /                   l      Licensed under GPLv3
  l  /       \        l
  j  ●   .   ●        l      """ + pacman_version + r"""
 { )  ._,.__,   , -.  {      pyalpm v""" + pyalpm_version + r"""
  У    \  _/     ._/   \

""")


def print_not_found_packages(not_found_packages: List[str], repo=False) -> None:
    num_packages = len(not_found_packages)
    print_warning(
        bold_line(
            _n(
                "Following package cannot be found in repositories:",
                "Following packages cannot be found in repositories:",
                num_packages
            )
            if repo else
            _n(
                "Following package cannot be found in AUR:",
                "Following packages cannot be found in AUR:",
                num_packages
            )
        )
    )
    for package in not_found_packages:
        print_stderr(format_paragraph(package))


class ColorGenerator:

    _type_storage: Dict[str, int] = {}
    _cache: Dict[str, Dict[str, int]] = {}
    _init_done = False

    @classmethod
    def do_init(cls) -> None:
        if cls._init_done:
            return

        cls._init_done = True
        for official_repo_name in OFFICIAL_REPOS:
            cls.get_next('repo', official_repo_name)
        for repo in PackageDB.get_alpm_handle().get_syncdbs():
            cls.get_next('repo', repo.name)

    @classmethod
    def get_next(cls, color_type: str, _id: str) -> int:
        cls.do_init()
        if cls._cache.get(color_type, {}).get(_id):
            return cls._cache[color_type][_id]

        if (
                not cls._type_storage.get(color_type) or
                cls._type_storage[color_type] >= 15
        ):
            cls._type_storage[color_type] = 10
        else:
            cls._type_storage[color_type] += 1

        cls._cache.setdefault(color_type, {})
        cls._cache[color_type][_id] = cls._type_storage[color_type]
        return cls._cache[color_type][_id]


def pretty_format_repo_name(repo_name: str, color=True) -> str:
    result = f'{repo_name}/'
    if not color:
        return result
    return color_line(result, ColorGenerator.get_next('repo', repo_name))


def pretty_format_upgradeable(  # pylint: disable=too-many-statements
        packages_updates: List['InstallInfo'],
        verbose=False, print_repo=False, color=True, template: str = None
) -> str:

    _color_line = color_line
    _bold_line = bold_line
    if not color:
        _color_line = lambda line, *args, **kwargs: line  # noqa
        _bold_line = lambda line: line  # noqa

    SortKey = Union[Tuple, str]

    def pretty_format(pkg_update: 'InstallInfo') -> Tuple[str, SortKey]:  # pylint:disable=too-many-locals
        common_version, diff_weight = get_common_version(
            pkg_update.current_version or '', pkg_update.new_version or ''
        )
        user_config = PikaurConfig()
        color_config = user_config.colors
        version_color = color_config.Version.get_int()
        old_color = color_config.VersionDiffOld.get_int()
        new_color = color_config.VersionDiffNew.get_int()
        column_width = min(int(get_term_width() / 2.5), 37)

        sort_by: SortKey = (
            -diff_weight,
            pkg_update.name
        )
        user_chosen_sorting = user_config.sync.UpgradeSorting
        if user_chosen_sorting == 'pkgname':
            sort_by = pkg_update.name
        elif user_chosen_sorting == 'repo':
            sort_by = (
                pkg_update.repository or 'zzz_(aur)',
                pkg_update.name
            )

        pkg_name = pkg_update.name
        pkg_len = len(pkg_update.name)

        pkg_name = _bold_line(pkg_name)
        if (print_repo or verbose) and pkg_update.repository:
            pkg_name = '{}{}'.format(
                pretty_format_repo_name(pkg_update.repository, color=color),
                pkg_name
            )
            pkg_len += len(pkg_update.repository) + 1
        elif print_repo:
            pkg_name = '{}{}'.format(
                _color_line('aur/', 9),
                pkg_name
            )
            pkg_len += len('aur/')

        if pkg_update.required_by:
            required_by = ' ({})'.format(
                _('for {pkg}').format(
                    pkg=', '.join([p.package.name for p in pkg_update.required_by])
                )
            )
            pkg_len += len(required_by)
            dep_color = 3
            required_by = _color_line(' ({})', dep_color).format(
                _('for {pkg}').format(
                    pkg=_color_line(', ', dep_color).join([
                        _color_line(p.package.name, dep_color + 8) for p in pkg_update.required_by
                    ]) + _color_line('', dep_color, reset=False),
                )
            )
            pkg_name += required_by
        if pkg_update.provided_by:
            provided_by = ' ({})'.format(
                ' # '.join([p.name for p in pkg_update.provided_by])
            )
            pkg_len += len(provided_by)
            pkg_name += _color_line(provided_by, 2)
        if pkg_update.members_of:
            members_of = ' ({})'.format(
                _n('{grp} group', '{grp} groups', len(pkg_update.members_of)).format(
                    grp=', '.join(g for g in pkg_update.members_of),
                )
            )
            pkg_len += len(members_of)
            members_of = _color_line(' ({})', GROUP_COLOR).format(
                _n('{grp} group', '{grp} groups', len(pkg_update.members_of)).format(
                    grp=_color_line(', ', GROUP_COLOR).join(
                        [_color_line(g, GROUP_COLOR + 8) for g in pkg_update.members_of]
                    ) + _color_line('', GROUP_COLOR, reset=False),
                )
            )
            pkg_name += _color_line(members_of, GROUP_COLOR)
        if pkg_update.replaces:
            replaces = ' (replaces {})'.format(
                ', '.join(g for g in pkg_update.replaces)
            )
            pkg_len += len(replaces)
            pkg_name += _color_line(replaces, REPLACEMENTS_COLOR)
            if not color:
                pkg_name = f'# {pkg_name}'

        pkg_size = ''
        if (
                user_config.sync.ShowDownloadSize.get_bool() and
                isinstance(pkg_update.package, pyalpm.Package)
        ):
            pkg_size = f'{pkg_update.package.size/1024/1024:.2f} MiB'

        days_old = ''
        if pkg_update.devel_pkg_age_days:
            days_old = ' ' + _('({} days old)').format(pkg_update.devel_pkg_age_days)

        out_of_date = ''
        if (
                isinstance(pkg_update.package, AURPackageInfo) and
                pkg_update.package.outofdate is not None
        ):
            out_of_date = _color_line(
                " [{}: {}]".format(
                    _("outofdate"),
                    datetime.fromtimestamp(pkg_update.package.outofdate).strftime('%Y/%m/%d')
                ),
                color_config.VersionDiffOld.get_int()
            )

        return (
            template or (
                ' {pkg_name}{spacing}'
                ' {current_version}{spacing2}'
                '{version_separator}{new_version}{spacing3}'
                '{pkg_size}{days_old}{out_of_date}{verbose}'
            )
        ).format(
            pkg_name=pkg_name,
            current_version=(
                _color_line(common_version, version_color) +
                _color_line(
                    get_version_diff(pkg_update.current_version or '', common_version),
                    old_color
                )
            ),
            new_version=(
                _color_line(common_version, version_color) +
                _color_line(
                    get_version_diff(pkg_update.new_version or '', common_version),
                    new_color
                )
            ),
            version_separator=(
                ' -> ' if (pkg_update.current_version or pkg_update.new_version) else ''
            ),
            spacing=' ' * max(1, (column_width - pkg_len)),
            spacing2=' ' * max(1, (
                column_width - 18 -
                len(pkg_update.current_version or '') -
                max(-1, (pkg_len - column_width))
            )),
            spacing3=(' ' * max(1, (
                column_width - 18 -
                len(pkg_update.new_version or '') -
                max(-1, (pkg_len - column_width))
            )) if pkg_size else ''),
            pkg_size=pkg_size,
            days_old=days_old,
            out_of_date=out_of_date,
            verbose=(
                '' if not (verbose and pkg_update.description)
                else f'\n{format_paragraph(pkg_update.description)}'
            )
        ), sort_by

    return '\n'.join([
        line for line, _ in sorted(
            [
                pretty_format(pkg_update)
                for pkg_update in packages_updates
            ],
            key=lambda x: x[1],
        )
    ])


def pretty_format_sysupgrade(
        install_info: 'InstallInfoFetcher',
        verbose=False,
        manual_package_selection=False
) -> str:

    color = True

    repo_packages_updates = install_info.repo_packages_install_info
    thirdparty_repo_packages_updates = install_info.thirdparty_repo_packages_install_info
    aur_updates = install_info.aur_updates_install_info
    repo_replacements = install_info.repo_replacements_install_info
    thirdparty_repo_replacements = install_info.thirdparty_repo_replacements_install_info

    new_repo_deps: Optional[List['InstallInfo']] = \
        install_info.new_repo_deps_install_info
    new_thirdparty_repo_deps: Optional[List['InstallInfo']] = \
        install_info.new_thirdparty_repo_deps_install_info
    new_aur_deps: Optional[List['InstallInfo']] = \
        install_info.aur_deps_install_info

    if manual_package_selection:
        color = False
        new_repo_deps = None
        new_thirdparty_repo_deps = None
        new_aur_deps = None

    _color_line = color_line
    _bold_line = bold_line
    if not color:
        _color_line = lambda line, *args: line  # noqa
        _bold_line = lambda line: line  # noqa

    result = []

    if repo_replacements:
        result.append('\n{} {}'.format(
            _color_line('::', 12),
            _bold_line(_n(
                "Repository package suggested as a replacement:",
                "Repository packages suggested as a replacement:",
                len(repo_replacements)))
        ))
        result.append(pretty_format_upgradeable(
            repo_replacements,
            verbose=verbose, color=color,
            print_repo=PikaurConfig().sync.AlwaysShowPkgOrigin.get_bool()
        ))
    if thirdparty_repo_replacements:
        result.append('\n{} {}'.format(
            _color_line('::', 12),
            _bold_line(_n(
                "Third-party repository package suggested as a replacement:",
                "Third-party repository packages suggested as a replacement:",
                len(repo_packages_updates)))
        ))
        result.append(pretty_format_upgradeable(
            thirdparty_repo_replacements,
            verbose=verbose, color=color,
            print_repo=PikaurConfig().sync.AlwaysShowPkgOrigin.get_bool()
        ))

    if repo_packages_updates:
        result.append('\n{} {}'.format(
            _color_line('::', 12),
            _bold_line(_n(
                "Repository package will be installed:",
                "Repository packages will be installed:",
                len(repo_packages_updates)))
        ))
        result.append(pretty_format_upgradeable(
            repo_packages_updates,
            verbose=verbose, color=color,
            print_repo=PikaurConfig().sync.AlwaysShowPkgOrigin.get_bool()
        ))
    if new_repo_deps:
        result.append('\n{} {}'.format(
            _color_line('::', 11),
            _bold_line(_n("New dependency will be installed from repository:",
                          "New dependencies will be installed from repository:",
                          len(new_repo_deps)))
        ))
        result.append(pretty_format_upgradeable(
            new_repo_deps,
            verbose=verbose, color=color,
            print_repo=PikaurConfig().sync.AlwaysShowPkgOrigin.get_bool()
        ))
    if thirdparty_repo_packages_updates:
        result.append('\n{} {}'.format(
            _color_line('::', 12),
            _bold_line(_n("Third-party repository package will be installed:",
                          "Third-party repository packages will be installed:",
                          len(thirdparty_repo_packages_updates)))
        ))
        result.append(pretty_format_upgradeable(
            thirdparty_repo_packages_updates,
            verbose=verbose, color=color, print_repo=True
        ))
    if new_thirdparty_repo_deps:
        result.append('\n{} {}'.format(
            _color_line('::', 11),
            _bold_line(_n("New dependency will be installed from third-party repository:",
                          "New dependencies will be installed from third-party repository:",
                          len(new_thirdparty_repo_deps)))
        ))
        result.append(pretty_format_upgradeable(
            new_thirdparty_repo_deps,
            verbose=verbose, color=color,
            print_repo=PikaurConfig().sync.AlwaysShowPkgOrigin.get_bool()
        ))
    if aur_updates:
        result.append('\n{} {}'.format(
            _color_line('::', 14),
            _bold_line(_n("AUR package will be installed:",
                          "AUR packages will be installed:",
                          len(aur_updates)))
        ))
        result.append(pretty_format_upgradeable(
            aur_updates,
            verbose=verbose, color=color, print_repo=False
        ))
    if new_aur_deps:
        result.append('\n{} {}'.format(
            _color_line('::', 11),
            _bold_line(_n("New dependency will be installed from AUR:",
                          "New dependencies will be installed from AUR:",
                          len(new_aur_deps)))
        ))
        result.append(pretty_format_upgradeable(
            new_aur_deps,
            verbose=verbose, color=color, print_repo=False
        ))
    result += ['']
    return '\n'.join(result)


def print_ignored_package(
        package_name: Optional[str] = None,
        install_info: Optional[InstallInfo] = None,
) -> None:
    if not (package_name or install_info):
        raise TypeError("Either 'package_name' or 'install_info' should be specified")
    install_info = install_info or InstallInfo(
        name=package_name,
        current_version='',
        new_version='',
        package=None,
    )
    print_stderr('{} {}'.format(
        color_line('::', 11),
        _("Ignoring package update {}").format(
            pretty_format_upgradeable(
                [install_info],
                template="{pkg_name} ({current_version} => {new_version})"
            ))
        if (install_info.current_version and install_info.new_version) else
        _("Ignoring package {}").format(
            pretty_format_upgradeable(
                [install_info],
                template=(
                    "{pkg_name} {current_version}"
                    if install_info.current_version else
                    "{pkg_name} {new_version}"
                )
            ))
    ))


def _get_local_version(package_name: str) -> str:
    return PackageDB.get_local_dict()[package_name].version


def print_package_uptodate(package_name: str, package_source: PackageSource) -> None:
    print_warning(
        _("{name} {version} {package_source} package is up to date - skipping").format(
            name=package_name,
            version=bold_line(_get_local_version(package_name)),
            package_source=package_source.name
        )
    )


def print_local_package_newer(package_name: str, aur_version: str) -> None:
    print_warning(
        _("{name} {version} local package is newer than in AUR ({aur_version}) - skipping").format(
            name=package_name,
            version=bold_line(_get_local_version(package_name)),
            aur_version=bold_line(aur_version),
        )
    )


def print_package_downgrading(package_name: str, downgrade_version: str) -> None:
    print_warning(
        _("Downgrading AUR package {name} {version} to {downgrade_version}").format(
            name=bold_line(package_name),
            version=bold_line(_get_local_version(package_name)),
            downgrade_version=bold_line(downgrade_version)
        )
    )


def print_ignoring_outofdate_upgrade(package_info: InstallInfo) -> None:
    print_warning(
        _("{name} {version} AUR package marked as 'outofdate' - skipping").format(
            name=package_info.name,
            version=bold_line(package_info.new_version),
        )
    )


# @TODO: weird pylint behavior if remove `return` from the end:
def print_package_search_results(  # pylint:disable=useless-return,too-many-locals,too-many-statements,too-many-branches
        repo_packages: Iterable[pyalpm.Package],
        aur_packages: Iterable[AURPackageInfo],
        local_pkgs_versions: Dict[str, str],
        enumerated=False,
) -> List[AnyPackage]:

    repos = [db.name for db in PackageDB.get_alpm_handle().get_syncdbs()]
    user_config = PikaurConfig()
    group_by_repo = user_config.ui.GroupByRepository.get_bool()

    def get_repo_sort_key(pkg: pyalpm.Package) -> Tuple[int, str]:
        return (
            repos.index(pkg.db.name)
            if group_by_repo and pkg.db.name in repos
            else 999,
            pkg.name
        )

    AurSortKey = Union[Tuple[float, float], float]

    def get_aur_sort_key(pkg: AURPackageInfo) -> Tuple[AurSortKey, str]:
        user_aur_sort = user_config.ui.AurSearchSorting
        pkg_numvotes = pkg.numvotes if isinstance(pkg.numvotes, int) else 0
        pkg_popularity = pkg.popularity if isinstance(pkg.popularity, float) else 0.0

        if user_aur_sort == 'pkgname':
            return (-1.0, pkg.name)
        if user_aur_sort == 'popularity':
            return ((-pkg_popularity, -pkg_numvotes), pkg.name)
        if user_aur_sort == 'numvotes':
            return ((-pkg_numvotes, -pkg_popularity), pkg.name)
        if user_aur_sort == 'lastmodified':
            return (
                -pkg.lastmodified
                if isinstance(pkg.lastmodified, int)
                else 0,
                pkg.name)
        return (-(pkg_numvotes + 1) * (pkg_popularity + 1), pkg.name)

    args = parse_args()
    local_pkgs_names = local_pkgs_versions.keys()

    sorted_repo_pkgs: List[pyalpm.Package] = list(sorted(
        repo_packages,
        key=get_repo_sort_key
    ))
    sorted_aur_pkgs: List[AURPackageInfo] = list(sorted(
        aur_packages,
        key=get_aur_sort_key
    ))
    sorted_packages: List[AnyPackage] = [*sorted_repo_pkgs, *sorted_aur_pkgs]
    # mypy is always funny ^^ https://github.com/python/mypy/issues/5492#issuecomment-545992992

    enumerated_packages = list(enumerate(sorted_packages))
    if user_config.ui.ReverseSearchSorting.get_bool():
        enumerated_packages = list(reversed(enumerated_packages))

    for pkg_idx, package in enumerated_packages:
        # @TODO: return only packages for the current architecture
        idx = ''
        if enumerated:
            idx = bold_line(f'{pkg_idx+1}) ')

        pkg_name = package.name
        if args.quiet:
            print(f'{idx}{pkg_name}')
        else:

            repo = color_line('aur/', 9)
            if isinstance(package, pyalpm.Package):
                repo = pretty_format_repo_name(package.db.name)

            groups = ''
            if getattr(package, 'groups', None):
                groups = color_line('({}) '.format(' '.join(package.groups)), GROUP_COLOR)

            installed = ''
            if pkg_name in local_pkgs_names:
                if package.version != local_pkgs_versions[pkg_name]:
                    installed = color_line(_("[installed: {version}]").format(
                        version=local_pkgs_versions[pkg_name],
                    ) + ' ', 14)
                else:
                    installed = color_line(_("[installed]") + ' ', 14)

            rating = ''
            if (
                    isinstance(package, AURPackageInfo)
            ) and (
                package.numvotes is not None
            ) and (
                package.popularity is not None
            ):
                rating = color_line('({}, {:.2f})'.format(
                    package.numvotes,
                    package.popularity
                ), 3)

            color_config = user_config.colors
            version_color = color_config.Version.get_int()
            version = package.version

            if isinstance(package, AURPackageInfo) and package.outofdate is not None:
                version_color = color_config.VersionDiffOld.get_int()
                version = "{} [{}: {}]".format(
                    package.version,
                    _("outofdate"),
                    datetime.fromtimestamp(package.outofdate).strftime('%Y/%m/%d')
                )

            last_updated = ""
            if user_config.ui.DisplayLastUpdated.get_bool():
                last_update_date = None

                if isinstance(package, pyalpm.Package):
                    last_update_date = package.builddate
                if isinstance(package, AURPackageInfo):
                    last_update_date = package.lastmodified

                last_updated = color_line(' (last updated: {})'.format(
                    datetime.fromtimestamp(last_update_date).strftime('%Y/%m/%d')
                    if last_update_date is not None
                    else 'unknown'
                ), 8)

            print("{}{}{} {} {}{}{}{}".format(
                idx,
                repo,
                bold_line(pkg_name),
                color_line(version, version_color),
                groups,
                installed,
                rating,
                last_updated
            ))
            print(format_paragraph(f'{package.desc}'))
    return sorted_packages
