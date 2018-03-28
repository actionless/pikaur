import sys
import shutil
from typing import List, TYPE_CHECKING, Callable, Tuple

from .config import VERSION, PikaurConfig
from .version import get_common_version, get_version_diff
from .i18n import _, _n

if TYPE_CHECKING:
    # pylint: disable=unused-import
    from .package_update import PackageUpdate  # noqa


PADDING = 4


def color_line(line: str, color_number: int) -> str:
    result = ''
    if color_number >= 8:
        result += "\033[1m"
        color_number -= 8
    result += f"\033[03{color_number}m{line}"
    # reset font:
    result += "\033[0m"
    return result


def bold_line(line: str) -> str:
    return f'\033[1m{line}\033[0m'


def get_term_width() -> int:
    return shutil.get_terminal_size((80, 80)).columns


def format_paragraph(line: str) -> str:
    term_width = get_term_width()
    max_line_width = term_width - PADDING * 2

    result = []
    current_line: List[str] = []
    line_length = 0
    for word in line.split():
        if len(word) + line_length > max_line_width:
            result.append(current_line)
            current_line = []
            line_length = 0
        current_line.append(word)
        line_length += len(word) + 1
    result.append(current_line)

    return '\n'.join([
        ' '.join(
            [(PADDING-1)*' ', ] +
            words +
            [(PADDING-1)*' ', ],
        )
        for words in result
    ])


def print_status_message(message='') -> None:
    sys.stderr.write(f'{message}\n')


def print_not_found_packages(not_found_packages: List[str]) -> None:
    print("{} {}".format(
        color_line(':: ' + _("warning:"), 11),
        bold_line(_("Following packages cannot be found in AUR:")),
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
        color_config = PikaurConfig().colors
        version_color: int = color_config.get('Version')  # type: ignore
        old_color: int = color_config.get('VersionDiffOld')  # type: ignore
        new_color: int = color_config.get('VersionDiffNew')  # type: ignore
        column_width = min(int(get_term_width() / 2.5), 37)
        sort_by = '{:03d}{}'.format(
            difference_size,
            pkg_update.Name
        )

        pkg_name = _bold_line(pkg_update.Name)
        pkg_len = len(pkg_update.Name)

        days_old = ''
        if pkg_update.devel_pkg_age_days:
            days_old = ' ' + _('({} days old)').format(pkg_update.devel_pkg_age_days)

        if (print_repo or verbose) and pkg_update.Repository:
            pkg_name = '{}{}'.format(
                _color_line(pkg_update.Repository + '/', 13),
                pkg_name
            )
            pkg_len += len(pkg_update.Repository) + 1

        return (
            template or (
                ' {pkg_name}{spacing}'
                ' {current_version}{spacing2} -> {new_version}{days_old}{verbose}'
            )
        ).format(
            pkg_name=pkg_name,
            days_old=days_old,
            current_version=_color_line(common_version, version_color) +
            _color_line(
                get_version_diff(pkg_update.Current_Version or '', common_version),
                old_color
            ),
            new_version=_color_line(common_version, version_color) +
            _color_line(
                get_version_diff(pkg_update.New_Version or '', common_version),
                new_color
            ),
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
        thirdparty_repo_packages_updates: List['PackageUpdate'] = None,
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
            print_repo=PikaurConfig().sync.get('AlwaysShowPkgOrigin')
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


def print_version(pacman_version: str, quiet=False) -> None:
    if quiet:
        print(f'Pikaur v{VERSION}')
        print(pacman_version)
    else:
        sys.stdout.buffer.write((r"""
      /:}               _
     /--1             / :}
    /   |           / `-/
   |  ,  --------  /   /
   |'                 Y      Pikaur v"""+VERSION+r"""
  /                   l      (C) 2018 Pikaur development team
  l  /       \        l      Licensed under GPLv3
  j  ●   .   ●        l
 { )  ._,.__,   , -.  {      """+pacman_version+r"""
  У    \  _/     ._/   \

""").encode())


class ProgressBar(object):

    message: str = None
    print_ratio: float = None
    index = 0
    progress = 0

    LEFT_DECORATION = '['
    RIGHT_DECORATION = ']'
    EMPTY = '-'
    FULL = '#'

    def __init__(self, length: int, message='') -> None:
        self.message = message
        width = (
            get_term_width() - len(message) -
            len(self.LEFT_DECORATION) - len(self.RIGHT_DECORATION)
        )
        self.print_ratio = length / width
        sys.stderr.write(message)
        sys.stderr.write(self.LEFT_DECORATION + self.EMPTY * width + self.RIGHT_DECORATION)
        sys.stderr.write(f'{(chr(27))}[\bb' * (width + len(self.RIGHT_DECORATION)))

    def update(self) -> None:
        self.index += 1
        if self.index / self.print_ratio > self.progress:
            self.progress += 1
            sys.stderr.write(self.FULL)

    def __enter__(self) -> Callable:
        return self.update

    def __exit__(self, *exc_details) -> None:
        sys.stderr.write('\n')
