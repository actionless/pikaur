import sys
import shutil

from .config import VERSION
from .version import compare_versions


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


def print_status_message(message=''):
    sys.stderr.write(f'{message}\n')


def print_not_found_packages(not_found_packages):
    print("{} {}".format(
        color_line(':: warning:', 11),
        bold_line('Following packages can not be found in AUR:'),
    ))
    for package in not_found_packages:
        print(format_paragraph(package))


VERSION_SEPARATORS = ('.', '+', '-', ':')


def pretty_format_upgradeable(
        packages_updates, verbose=False, print_repo=False, color=True, template=None
):

    _color_line = color_line
    _bold_line = bold_line
    if not color:
        _color_line = _bold_line = lambda x, *args: x

    def split_version(version):
        splitted_version = []
        block = ''
        for char in version:
            if char in VERSION_SEPARATORS:
                splitted_version.append(block)
                splitted_version.append(char)
                block = ''
            else:
                block += char
        if block != '':
            splitted_version.append(block)
        return splitted_version

    def get_common_version(version1, version2):
        common_string = ''
        common_length = 0
        if '' in (version1, version2):
            return common_string, common_length
        for block1, block2 in zip(
                split_version(version1),
                split_version(version2)
        ):
            if compare_versions(block1, block2) == 0:
                common_string += block1
                if block1 not in VERSION_SEPARATORS:
                    common_length += 1
            else:
                break
        return common_string, common_length

    def get_version_diff(version, common_version):
        new_version_postfix = version
        if common_version != '':
            _new_version_postfix = version.split(
                common_version
            )[1:]
            new_version_postfix = common_version.join(_new_version_postfix)
        return new_version_postfix

    def pretty_format(pkg_update, template):
        common_version, difference_size = get_common_version(
            pkg_update.Current_Version, pkg_update.New_Version
        )
        version_color = 10
        old_color = 11
        new_color = 9
        column_width = min(int(get_term_width() / 2.5), 37)
        sort_by = '{:03d}{}'.format(
            difference_size,
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
        return (
            template or ' {pkg_name}{spacing} {current_version}{spacing2} -> {new_version}{verbose}'
        ).format(
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
                pretty_format(pkg_update, template=template)
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


def pretty_format_repo_name(repo_name):
    return color_line(f'{repo_name}/', len(repo_name) % 5 + 10)


def print_package_search_results(packages, local_pkgs_versions, args):
    def get_sort_key(pkg):
        if getattr(pkg, "numvotes", None):
            return (pkg.numvotes + 0.1) * (pkg.popularity + 0.1)
        return 1

    local_pkgs_names = local_pkgs_versions.keys()
    for package in sorted(
            packages,
            key=get_sort_key,
            reverse=True
    ):
        # @TODO: return only packages for the current architecture
        pkg_name = package.name
        if args.quiet:
            print(pkg_name)
        else:

            repo = color_line('aur/', 9)
            if getattr(package, 'db', None):
                repo = pretty_format_repo_name(package.db.name)

            groups = ''
            if getattr(package, 'groups', None):
                groups = color_line('({}) '.format(' '.join(package.groups)), 4)

            installed = ''
            if pkg_name in local_pkgs_names:
                installed = color_line('[installed{}] '.format(
                    f': {local_pkgs_versions[pkg_name]}'
                    if package.version != local_pkgs_versions[pkg_name]
                    else ''
                ), 14)

            rating = ''
            if getattr(package, "numvotes", None):
                rating = color_line('({}, {:.2f})'.format(
                    package.numvotes,
                    package.popularity
                ), 3)

            print("{}{} {} {}{}{}".format(
                repo,
                bold_line(pkg_name),
                color_line(package.version, 10),
                groups,
                installed,
                rating
            ))
            print(format_paragraph(f'{package.desc}'))


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

    def __init__(self, length, message=''):
        self.message = message
        width = get_term_width() - len(message)
        self.print_ratio = length / width
        sys.stderr.write(message)

    def update(self):
        self.index += 1
        if self.index / self.print_ratio > self.progress:
            self.progress += 1
            sys.stderr.write('.')
            sys.stderr.flush()

    def __enter__(self):
        return self.update

    def __exit__(self, *exc_details):
        sys.stderr.write('\n')
