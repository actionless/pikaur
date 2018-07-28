""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import sys
from argparse import Namespace  # pylint: disable=no-name-in-module
from typing import Any, List, NoReturn, Optional, Tuple, Union

from .argparse import ArgumentParserWithUnknowns
from .core import spawn
from .config import PikaurConfig
from .i18n import _, _n


ArgSchema = List[Tuple[Optional[str], str, Union[None, bool, str]]]


PACMAN_BOOL_OPTS: ArgSchema = [
    ('S', 'sync', None),
    ('g', 'groups', None),
    ('i', 'info', None),
    ('w', 'downloadonly', None),
    ('q', 'quiet', None),
    ('s', 'search', None),
    ('u', 'sysupgrade', None),
    ('d', 'nodeps', None),
    #
    ('h', 'help', None),
    ('V', 'version', None),
    ('D', 'database', None),
    ('F', 'files', None),
    ('Q', 'query', None),
    ('R', 'remove', None),
    ('T', 'deptest', None),
    ('U', 'upgrade', None),
    #
    (None, 'noconfirm', None),
    (None, 'needed', None),
]


def get_pikaur_bool_opts() -> ArgSchema:
    return [
        (None, 'noedit', PikaurConfig().build.get_bool('NoEdit')),
        (None, 'edit', None),
        (None, 'namesonly', None),
        (None, 'repo', None),
        ('a', 'aur', None),
        (None, 'devel', None),
        ('k', 'keepbuild', PikaurConfig().build.get_bool('KeepBuildDir')),
        (None, 'nodiff', PikaurConfig().build.get_bool('NoDiff')),
        (None, 'rebuild', None),
        (None, 'dynamic-users', PikaurConfig().build.get_bool('AlwaysUseDynamicUsers')),
        ('P', 'pkgbuild', None),
        (None, 'install', None),
        ('G', 'getpkgbuild', None),
        (None, 'deps', None),
        # undocumented options:
        (None, 'debug', PikaurConfig().misc.get_bool('Debug')),
        (None, 'print-commands', PikaurConfig().ui.get_bool('PrintCommands')),
        (None, 'hide-build-log', None),
    ]


PACMAN_STR_OPTS: ArgSchema = [
    (None, 'color', None),
    ('r', 'root', None),
]


def get_pikaur_str_opts() -> ArgSchema:
    return [
        (None, 'mflags', None),
        (None, 'makepkg-config', None),
        (None, 'makepkg-path', None),
    ]


class IncompatibleArguments(Exception):
    pass


class MissingArgument(Exception):
    pass


class PikaurArgs(Namespace):
    unknown_args: List[str]
    raw: List[str]

    def __getattr__(self, name: str) -> Any:
        """
        this is a hack for typing/mypy
        """
        return getattr(super(), name)

    def handle_the_same_letter(self):
        # pylint: disable=attribute-defined-outside-init,access-member-before-definition
        # type: ignore
        if self.pkgbuild and self.info:  # handle "-i"
            self.install = self.info
            self.info = False
        if self.getpkgbuild and self.nodeps:  # handle "-d"
            self.deps = self.nodeps
            self.nodeps = False
        if self.debug:
            self.print_commands = self.debug

    def validate(self) -> None:
        if self.query:
            if not self.sysupgrade:
                for arg_name in ('aur', 'repo'):
                    if getattr(self, arg_name):
                        raise MissingArgument('sysupgrade', arg_name)

    @classmethod
    def from_namespace(
            cls,
            namespace: Namespace,
            unknown_args: List[str],
            raw_args: List[str]
    ) -> 'PikaurArgs':
        result = cls()
        for key, value in namespace.__dict__.items():
            setattr(result, key, value)
        result.unknown_args = unknown_args
        result.raw = raw_args
        result.handle_the_same_letter()
        return result


class PikaurArgumentParser(ArgumentParserWithUnknowns):

    def error(self, message: str) -> NoReturn:
        exc = sys.exc_info()[1]
        if exc:
            raise exc
        super().error(message)

    def parse_pikaur_args(self, raw_args: List[str]) -> PikaurArgs:
        parsed_args, unknown_args = self.parse_known_args(raw_args)
        for arg in unknown_args[:]:
            if arg.startswith('-'):
                continue
            unknown_args.remove(arg)
            parsed_args.positional.append(arg)
        return PikaurArgs.from_namespace(
            namespace=parsed_args,
            unknown_args=unknown_args,
            raw_args=raw_args
        )

    def add_letter_andor_opt(
            self,
            action: str = None,
            letter: str = None, opt: str = None,
            default: Any = None
    ) -> None:
        if letter and opt:
            self.add_argument(  # type: ignore
                '-' + letter, '--' + opt, action=action, default=default
            )
        elif opt:
            self.add_argument(  # type: ignore
                '--' + opt, action=action, default=default
            )
        elif letter:
            self.add_argument(  # type: ignore
                '-' + letter, action=action, default=default
            )


class CachedArgs():

    args: Optional[PikaurArgs] = None


def parse_args(args: List[str] = None) -> PikaurArgs:
    if CachedArgs.args:
        return CachedArgs.args
    args = args or sys.argv[1:]
    parser = PikaurArgumentParser(prog=sys.argv[0], add_help=False)

    # add some of pacman options to argparser to have them registered by pikaur
    # (they will be bypassed to pacman with the rest unrecognized args anyway)

    for letter, opt, default in PACMAN_BOOL_OPTS + get_pikaur_bool_opts():
        parser.add_letter_andor_opt(
            action='store_true', letter=letter, opt=opt, default=default
        )

    for letter, opt, default in [
            ('y', 'refresh', None),
            ('c', 'clean', None),
    ]:
        parser.add_letter_andor_opt(
            action='count', letter=letter, opt=opt, default=default
        )

    for letter, opt, default in PACMAN_STR_OPTS + get_pikaur_str_opts():
        parser.add_letter_andor_opt(
            action=None, letter=letter, opt=opt, default=default
        )

    parser.add_argument('--ignore', action='append')
    parser.add_argument('positional', nargs='*')

    parsed_args = parser.parse_pikaur_args(args)

    # print("ARGPARSE:")
    # print(parsed_args)
    # print(f'args = {args}')
    # print(parsed_args.unknown_args)
    # print(reconstruct_args(parsed_args))
    # print(reconstruct_args(parsed_args, ignore_args=['sync']))
    # sys.exit(0)

    try:
        parsed_args.validate()
    except IncompatibleArguments as exc:
        print(_(":: error: options {} can't be used together.").format(
            ", ".join([f"'--{opt}'" for opt in exc.args])
        ))
        sys.exit(1)
    except MissingArgument as exc:
        print(
            _n(
                ":: error: option {} can't be used without {}.",
                ":: error: options {} can't be used without {}.",
                len(exc.args[1:])
            ).format(
                ", ".join([f"'--{opt}'" for opt in exc.args[1:]]),
                f"'--{exc.args[0]}'"
            )
        )
        sys.exit(1)
    CachedArgs.args = parsed_args
    return parsed_args


def reconstruct_args(parsed_args: PikaurArgs, ignore_args: List[str] = None) -> List[str]:
    if not ignore_args:
        ignore_args = []
    for letter, opt, _default in get_pikaur_bool_opts() + get_pikaur_str_opts():
        if letter:
            ignore_args.append(letter)
        if opt:
            ignore_args.append(opt.replace('-', '_'))
    reconstructed_args = {
        f'--{key}' if len(key) > 1 else f'-{key}': value
        for key, value in parsed_args.__dict__.items()
        if value
        if key not in ignore_args + ['raw', 'unknown_args', 'positional', 'color', 'root']
    }
    return list(set(
        list(reconstructed_args.keys()) + parsed_args.unknown_args
    ))


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

    pikaur_long_opts = [
        long_opt
        for _short_opt, long_opt, _default in get_pikaur_bool_opts() + get_pikaur_str_opts()
    ]

    pacman_help = spawn(
        [PikaurConfig().misc.PacmanPath, ] + reconstruct_args(args, ignore_args=pikaur_long_opts),
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
    if args.sync or args.query:
        pikaur_options_help += [
            ('-a', '--aur', _("query packages from AUR only")),
            ('-r', '--repo', _("query packages from repository only")),
        ]
    if args.pkgbuild:
        pikaur_options_help += [
            ('-i', '--install', _("install built package")),
        ]
    if args.getpkgbuild:
        pikaur_options_help += [
            ('-d', '--deps', _("download also AUR dependencies")),
        ]
    if args.sync or args.pkgbuild:
        pikaur_options_help += [
            ('', '--noedit', _("don't prompt to edit PKGBUILDs and other build files")),
            ('', '--edit', _("prompt to edit PKGBUILDs and other build files")),
            ('-k', '--keepbuild', _("don't remove build dir after the build")),
            ('', '--rebuild', _("always rebuild AUR packages")),
            ('', '--mflags=<--flag1>,<--flag2>', _("cli args to pass to makepkg")),
            ('', '--makepkg-config=<path>', _("path to custom makepkg config")),
            ('', '--makepkg-path=<path>', _("override path to makepkg executable")),
            ('', '--dynamic-users', _("always isolate with systemd dynamic users")),
        ]
    if args.sync:
        pikaur_options_help += [
            ('', '--namesonly', _("search only in package names")),
            ('', '--devel', _("always sysupgrade '-git', '-svn' and other dev packages")),
            ('', '--nodiff', _("don't prompt to show the build files diff")),
        ]
    print(''.join([
        '\n',
        pacman_help,
        '\n\n' + _('Pikaur-specific options:') + '\n' if pikaur_options_help else '',
        _format_options_help(pikaur_options_help),
    ]))
