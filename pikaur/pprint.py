import sys
import shutil

from .config import VERSION


PADDING = 4


def color_line(line, color_number):
    result = ''
    if color_number >= 8:
        result += "\033[1m"
        color_number -= 8
    result += f"\033[03{color_number}m{line}"
    # reset font:
    result += "\033[0m"
    return result


def bold_line(line):
    return f'\033[1m{line}\033[0m'


def get_term_width():
    return shutil.get_terminal_size((80, 80)).columns


def format_paragraph(line):
    term_width = get_term_width()
    max_line_width = term_width - PADDING * 2

    result = []
    current_line = []
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


def print_not_found_packages(not_found_packages):
    print("{} {}".format(
        color_line(':: warning:', 11),
        bold_line('Following packages can not be found in AUR:'),
    ))
    for package in not_found_packages:
        print(format_paragraph(package))


def pretty_format_upgradeable(packages_updates, verbose=False, print_repo=False, color=True):

    _color_line = color_line
    _bold_line = bold_line
    if not color:
        _color_line = _bold_line = lambda x, *args: x

    def get_common_version(str1, str2):
        version_delimiters = ':.-+'

        result = str2
        while not str1.startswith(result):
            result = result[:-1]

        while len(result) > 0 and result[-1] not in version_delimeters:
            result = result[:-1]

        return result

    def get_version_diff(version, common_version):
        new_version_postfix = version
        if common_version != '':
            _new_version_postfix = version.split(
                common_version
            )[1:]
            new_version_postfix = common_version.join(_new_version_postfix)
        return new_version_postfix

    def pretty_format(pkg_update):
        common_version = get_common_version(
            pkg_update.Current_Version, pkg_update.New_Version
        )
        version_color = 10
        old_color = 11
        new_color = 9
        column_width = min(int(get_term_width() / 2.5), 37)
        sort_by = '{:03d}{}'.format(
            len(common_version)*10+len(pkg_update.New_Version),
            pkg_update.Name
        )
        pkg_name = _bold_line(pkg_update.Name)
        pkg_len = len(pkg_update.Name)
        if (print_repo or verbose) and pkg_update.Repository:
            pkg_name = '{}{}'.format(
                _color_line(pkg_update.Repository + '/', 13),
                pkg_name
            )
            pkg_len += len(pkg_update.Repository) + 1
        return ' {pkg_name}{spacing} {current_version}{spacing2} -> {new_version}{verbose}'.format(
            pkg_name=pkg_name,
            current_version=_color_line(common_version, version_color) +
            _color_line(
                get_version_diff(pkg_update.Current_Version, common_version),
                old_color
            ),
            new_version=_color_line(common_version, version_color) +
            _color_line(
                get_version_diff(pkg_update.New_Version, common_version),
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
        f'{line}' for line, _ in sorted(
            [
                pretty_format(pkg_update)
                for pkg_update in packages_updates
            ],
            key=lambda x: x[1],
        )
    ])


def print_upgradeable(packages_updates):
    print('\n'.join([
        pkg_update.Name
        for pkg_update in packages_updates
    ]))


def pretty_format_sysupgrade(  # pylint: disable=too-many-arguments
        repo_packages_updates=None, thirdparty_repo_packages_updates=None,
        aur_updates=None, new_aur_deps=None,
        verbose=False, color=True
):

    _color_line = color_line
    _bold_line = bold_line
    if not color:
        _color_line = _bold_line = lambda x, *args: x

    result = []
    if repo_packages_updates:
        result.append('\n{} {}'.format(
            _color_line('::', 12),
            _bold_line('Repository package{plural} will be installed:'.format(
                plural='s' if len(repo_packages_updates) > 1 else ''
            ))
        ))
        result.append(pretty_format_upgradeable(
            repo_packages_updates, verbose=verbose, color=color
        ))
    if thirdparty_repo_packages_updates:
        result.append('\n{} {}'.format(
            _color_line('::', 12),
            _bold_line('Third-party repository package{plural} will be installed:'.format(
                plural='s' if len(thirdparty_repo_packages_updates) > 1 else ''
            ))
        ))
        result.append(pretty_format_upgradeable(
            thirdparty_repo_packages_updates, verbose=verbose, print_repo=True, color=color
        ))
    if aur_updates:
        result.append('\n{} {}'.format(
            _color_line('::', 14),
            _bold_line('AUR package{plural} will be installed:'.format(
                plural='s' if len(aur_updates) > 1 else ''
            ))
        ))
        result.append(pretty_format_upgradeable(
            aur_updates, verbose=verbose, color=color
        ))
    if new_aur_deps:
        result.append('\n{} {}'.format(
            _color_line('::', 11),
            _bold_line('New dependenc{plural} will be installed from AUR:'.format(
                plural='ies' if len(new_aur_deps) > 1 else 'y'
            ))
        ))
        result.append(pretty_format_upgradeable(
            new_aur_deps, verbose=verbose, color=color
        ))
    result += ['']
    return '\n'.join(result)


def print_aur_search_results(aur_results, local_pkgs_versions, args):
    local_pkgs_names = local_pkgs_versions.keys()
    for aur_pkg in sorted(
            aur_results,
            key=lambda pkg: (pkg.NumVotes + 0.1) * (pkg.Popularity + 0.1),
            reverse=True
    ):
        # @TODO: return only packages for the current architecture
        pkg_name = aur_pkg.Name
        if args.quiet:
            print(pkg_name)
        else:
            print("{}{} {} {}({}, {:.2f})".format(
                # color_line('aur/', 13),
                color_line('aur/', 9),
                bold_line(pkg_name),
                color_line(aur_pkg.Version, 10),
                color_line('[installed{}] '.format(
                    f': {local_pkgs_versions[pkg_name]}'
                    if aur_pkg.Version != local_pkgs_versions[pkg_name]
                    else ''
                ), 14) if pkg_name in local_pkgs_names else '',
                aur_pkg.NumVotes,
                aur_pkg.Popularity
            ))
            print(format_paragraph(f'{aur_pkg.Description}'))


def print_version(pacman_version):
    sys.stdout.buffer.write((r"""
      /:}               _
     /--1             / :}
    /   |           / `-/
   |  ,  --------  /   /
   |'                 Y      Pikaur """+VERSION+r"""
  /                   l      (C) 2018 Pikaur development team
  l  /       \        l      Licensed under GPLv3
  j  ●   .   ●        l
 { )  ._,.__,   , -.  {      """+pacman_version+r"""
  У    \  _/     ._/   \

""").encode())


class ProgressBar(object):

    message = None
    print_ratio = None
    index = 0
    progress = 0

    def __init__(self, message, length):
        self.message = message
        width = get_term_width() - len(message)
        self.print_ratio = length / width
        print(message, end='')

    def update(self):
        self.index += 1
        if self.index / self.print_ratio > self.progress:
            self.progress += 1
            print('.', end='')
            sys.stdout.flush()

    def __enter__(self):
        return self.update

    def __exit__(self, *exc_details):
        print()
