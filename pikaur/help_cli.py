from typing import List, Tuple

from .i18n import _
from .args import (
    PikaurConfig,
    parse_args, reconstruct_args,
    get_pikaur_long_opts,
)
from .core import spawn


def _format_options_help(options: List[Tuple[str, str, str]]) -> str:
    return '\n'.join([
        '{:>5} {:<16} {}'.format(
            short_opt and (short_opt + ',') or '',
            long_opt or '',
            descr if ((len(short_opt) + len(long_opt)) < 16) else f"\n{23 * ' '}{descr}"
        )
        for short_opt, long_opt, descr in options
    ])


def cli_print_help() -> None:
    args = parse_args()

    pacman_help = spawn(
        [PikaurConfig().misc.PacmanPath.get_str(), ] +
        reconstruct_args(args, ignore_args=get_pikaur_long_opts()),
    ).stdout_text.replace(
        'pacman', 'pikaur'
    ).replace(
        'options:', '\n' + _("Common pacman options:")
    )
    if '--help' in pacman_help:
        pacman_help += (
            "\n" +
            _("pikaur-specific operations:") + "\n    " +
            _("pikaur {-P --pkgbuild}    [options] <file(s)>") + '\n    ' +
            _("pikaur {-G --getpkgbuild} [options] <package(s)>")
        )
    if args.pkgbuild:
        pacman_help = (
            _("usage:  pikaur {-P --pkgbuild} [options] <file(s)>") + "\n\n" +
            _("All common pacman options as when doing `pacman -U <pkg_file>`. See `pacman -Uh`.")
        )
    if args.getpkgbuild:
        pacman_help = (
            _("usage:  pikaur {-G --getpkgbuild} [options] <package(s)>")
        )

    pikaur_options_help: List[Tuple[str, str, str]] = []
    if args.getpkgbuild:
        pikaur_options_help += [
            ('-d', '--deps', _("download also AUR dependencies")),
        ]
    if args.pkgbuild:
        pikaur_options_help += [
            ('-i', '--install', _("install built package")),
        ]
    if args.sync or args.query or args.pkgbuild:
        pikaur_options_help += [
            ('-a', '--aur', _("query packages from AUR only")),
        ]
    if args.query:
        pikaur_options_help += [
            ('', '--repo', _("query packages from repository only")),
        ]
    if args.sync or args.pkgbuild:
        pikaur_options_help += [
            ('-o', '--repo', _("query packages from repository only")),
            ('', '--noedit', _("don't prompt to edit PKGBUILDs and other build files")),
            ('', '--edit', _("prompt to edit PKGBUILDs and other build files")),
            ('-k', '--keepbuild', _("don't remove build dir after the build")),
            ('', '--rebuild', _("always rebuild AUR packages")),
            ('', '--mflags=<--flag1>,<--flag2>', _("cli args to pass to makepkg")),
            ('', '--makepkg-config=<path>', _("path to custom makepkg config")),
            ('', '--makepkg-path=<path>', _("override path to makepkg executable")),
            ('', '--pikaur-config=<path>', _("path to custom pikaur config")),
            ('', '--dynamic-users', _("always isolate with systemd dynamic users")),
        ]
    if args.sync:
        pikaur_options_help += [
            ('', '--namesonly', _("search only in package names")),
            ('', '--devel', _("always sysupgrade '-git', '-svn' and other dev packages")),
            ('', '--nodiff', _("don't prompt to show the build files diff")),
            ('', '--ignore-outofdate', _("ignore AUR packages' updates which marked 'outofdate'")),
        ]

    if pikaur_options_help:  # if it's not just `pikaur --help`
        pikaur_options_help += [
            ('', '--pikaur-debug', _("show only debug messages specific to pikaur")),
        ]

    print(''.join([
        pacman_help,
        '\n\n' + _('Pikaur-specific options:') + '\n' if pikaur_options_help else '',
        _format_options_help(pikaur_options_help),
    ]))
