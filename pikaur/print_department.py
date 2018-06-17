import sys
from typing import List, Tuple

from .i18n import _, _n
from .pprint import (
    print_stderr, color_line, bold_line, format_paragraph, get_term_width,
)
from .core import PackageSource, InstallInfo
from .config import VERSION, PikaurConfig
from .version import get_common_version, get_version_diff
from .pacman import PackageDB
from .updates import get_remote_package_version


GROUP_COLOR = 4


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
        packages_updates: List['InstallInfo'],
        verbose=False, print_repo=False, color=True, template: str = None
) -> str:

    _color_line = color_line
    _bold_line = bold_line
    if not color:
        _color_line = lambda line, color: line  # noqa
        _bold_line = lambda line: line  # noqa

    def pretty_format(pkg_update: 'InstallInfo') -> Tuple[str, str]:  # pylint:disable=too-many-locals
        common_version, difference_size = get_common_version(
            pkg_update.current_version or '', pkg_update.new_version or ''
        )
        user_config = PikaurConfig()
        color_config = user_config.colors
        version_color = color_config.get_int('Version')
        old_color = color_config.get_int('VersionDiffOld')
        new_color = color_config.get_int('VersionDiffNew')
        column_width = min(int(get_term_width() / 2.5), 37)

        sort_by = '{:03d}{}'.format(
            difference_size,
            pkg_update.name
        )
        user_chosen_sorting = user_config.sync.UpgradeSorting
        if user_chosen_sorting == 'pkgname':
            sort_by = pkg_update.name
        elif user_chosen_sorting == 'repo':
            sort_by = '{}{}'.format(
                pkg_update.repository,
                pkg_update.name
            )

        pkg_name = pkg_update.name
        pkg_len = len(pkg_update.name)

        days_old = ''
        if pkg_update.devel_pkg_age_days:
            days_old = ' ' + _('({} days old)').format(pkg_update.devel_pkg_age_days)

        pkg_name = _bold_line(pkg_name)
        if (print_repo or verbose) and pkg_update.repository:
            pkg_name = '{}{}'.format(
                _color_line(pkg_update.repository + '/', 13),
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
            required_by = ' ({} {})'.format(
                _('for'),
                ', '.join([p.package.name for p in pkg_update.required_by])
            )
            pkg_len += len(required_by)
            dep_color = 3
            required_by = ' {} {}{}'.format(
                _color_line('(' + _('for'), dep_color),
                _color_line(', ', dep_color).join([
                    _color_line(p.package.name, dep_color + 8) for p in pkg_update.required_by
                ]),
                _color_line(')', dep_color),
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
                ', '.join([g for g in pkg_update.members_of])
            )
            pkg_len += len(members_of)
            pkg_name += _color_line(members_of, GROUP_COLOR)

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


def pretty_format_sysupgrade(  # pylint: disable=too-many-arguments
        repo_packages_updates: List['InstallInfo'] = None,
        new_repo_deps: List['InstallInfo'] = None,
        thirdparty_repo_packages_updates: List['InstallInfo'] = None,
        new_thirdparty_repo_deps: List['InstallInfo'] = None,
        aur_updates: List['InstallInfo'] = None,
        new_aur_deps: List['InstallInfo'] = None,
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


def print_ignored_package(package_name):
    current = PackageDB.get_local_dict().get(package_name)
    current_version = current.version if current else ''
    new_version = get_remote_package_version(package_name)
    print_stderr('{} {}'.format(
        color_line('::', 11),
        _("Ignoring package {}").format(
            pretty_format_upgradeable(
                [InstallInfo(
                    name=package_name,
                    current_version=current_version,
                    new_version=new_version or '',
                    package=None,
                )],
                template=(
                    "{pkg_name} ({current_version} => {new_version})"
                    if current_version else
                    "{pkg_name} {new_version}"
                )
            ))
    ))


def print_package_uptodate(package_name: str, package_source: PackageSource) -> None:
    print_stderr(
        '{} {}'.format(
            color_line(_("warning:"), 11),
            _("{name} {version} {package_source} package is up to date - skipping").format(
                name=package_name,
                version=bold_line(
                    PackageDB.get_local_dict()[package_name].version
                ),
                package_source=package_source.name
            )
        )
    )
