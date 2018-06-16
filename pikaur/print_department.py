import sys
from typing import List, TYPE_CHECKING, Tuple

from .i18n import _, _n
from .pprint import color_line, bold_line, format_paragraph, get_term_width
from .config import VERSION, PikaurConfig
from .version import get_common_version, get_version_diff

if TYPE_CHECKING:
    # pylint: disable=unused-import
    from .package_update import PackageUpdate  # noqa


def print_version(pacman_version: str, quiet=False) -> None:
    if quiet:
        print(f'Pikaur v{VERSION}')
        print(pacman_version)
    else:
        sys.stdout.write(r"""
      /:}               _
     /--1             / :}
    /   |           / `-/
   |  ,  --------  /   /
   |'                 Y      Pikaur v""" + VERSION + r"""
  /                   l      (C) 2018 Pikaur development team
  l  /       \        l      Licensed under GPLv3
  j  ●   .   ●        l
 { )  ._,.__,   , -.  {      """ + pacman_version + r"""
  У    \  _/     ._/   \

""")


def print_not_found_packages(not_found_packages: List[str], repo=False) -> None:
    print("{} {}".format(
        color_line(':: ' + _("warning:"), 11),
        (
            bold_line(_("Following packages cannot be found in repositories:"))
            if repo else
            bold_line(_("Following packages cannot be found in AUR:"))
        ),
    ))
    for package in not_found_packages:
        print(format_paragraph(package))


def pretty_format_upgradeable(
        packages_updates: List['PackageUpdate'],
        verbose=False, print_repo=False, color=True, template: str = None
) -> str:

    _color_line = color_line
    _bold_line = bold_line
    if not color:
        _color_line = lambda line, color: line  # noqa
        _bold_line = lambda line: line  # noqa

    def pretty_format(pkg_update: 'PackageUpdate') -> Tuple[str, str]:
        common_version, difference_size = get_common_version(
            pkg_update.Current_Version or '', pkg_update.New_Version or ''
        )
        user_config = PikaurConfig()
        color_config = user_config.colors
        version_color = color_config.get_int('Version')
        old_color = color_config.get_int('VersionDiffOld')
        new_color = color_config.get_int('VersionDiffNew')
        column_width = min(int(get_term_width() / 2.5), 37)

        sort_by = '{:03d}{}'.format(
            difference_size,
            pkg_update.Name
        )
        user_chosen_sorting = user_config.sync.UpgradeSorting
        if user_chosen_sorting == 'pkgname':
            sort_by = pkg_update.Name
        elif user_chosen_sorting == 'repo':
            sort_by = '{}{}'.format(
                pkg_update.Repository,
                pkg_update.Name
            )

        pkg_name = pkg_update.Name
        pkg_len = len(pkg_update.Name)

        days_old = ''
        if pkg_update.devel_pkg_age_days:
            days_old = ' ' + _('({} days old)').format(pkg_update.devel_pkg_age_days)

        pkg_name = _bold_line(pkg_name)
        if (print_repo or verbose) and pkg_update.Repository:
            pkg_name = '{}{}'.format(
                _color_line(pkg_update.Repository + '/', 13),
                pkg_name
            )
            pkg_len += len(pkg_update.Repository) + 1
        elif print_repo:
            pkg_name = '{}{}'.format(
                _color_line('aur/', 9),
                pkg_name
            )
            pkg_len += len('aur/')
        if pkg_update.provided_by:
            provided_by = ' ({})'.format(' # '.join([p.package.name for p in pkg_update.provided_by]))
            pkg_name += provided_by
            pkg_len += len(provided_by)

        return (
            template or (
                ' {pkg_name}{spacing}'
                ' {current_version}{spacing2}{version_separator}{new_version}{days_old}{verbose}'
            )
        ).format(
            pkg_name=pkg_name,
            days_old=days_old,
            current_version=(
                _color_line(common_version, version_color) +
                _color_line(
                    get_version_diff(pkg_update.Current_Version or '', common_version),
                    old_color
                )
            ),
            new_version=(
                _color_line(common_version, version_color) +
                _color_line(
                    get_version_diff(pkg_update.New_Version or '', common_version),
                    new_color
                )
            ),
            version_separator=' -> ' if (pkg_update.Current_Version or pkg_update.New_Version) else '',
            spacing=' ' * (column_width - pkg_len),
            spacing2=' ' * (column_width - len(pkg_update.Current_Version or '') - 18),
            verbose=(
                '' if not (verbose and pkg_update.Description)
                else f'\n{format_paragraph(pkg_update.Description)}'
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


def pretty_format_sysupgrade(  # pylint: disable=too-many-arguments
        repo_packages_updates: List['PackageUpdate'] = None,
        new_repo_deps: List['PackageUpdate'] = None,
        thirdparty_repo_packages_updates: List['PackageUpdate'] = None,
        new_thirdparty_repo_deps: List['PackageUpdate'] = None,
        aur_updates: List['PackageUpdate'] = None,
        new_aur_deps: List['PackageUpdate'] = None,
        verbose=False, color=True
) -> str:

    _color_line = color_line
    _bold_line = bold_line
    if not color:
        _color_line = lambda line, color: line  # noqa
        _bold_line = lambda line: line  # noqa

    result = []
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
            print_repo=PikaurConfig().sync.get_bool('AlwaysShowPkgOrigin')
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
            print_repo=PikaurConfig().sync.get_bool('AlwaysShowPkgOrigin')
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
            print_repo=PikaurConfig().sync.get_bool('AlwaysShowPkgOrigin')
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


def pretty_format_repo_name(repo_name: str) -> str:
    return color_line(f'{repo_name}/', len(repo_name) % 5 + 10)
