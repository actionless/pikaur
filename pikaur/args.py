""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import sys
from argparse import Namespace  # pylint: disable=no-name-in-module
from typing import Any, List, NoReturn, Optional, Tuple, Union

from .argparse import ArgumentParserWithUnknowns
from .core import spawn
from .config import PikaurConfig
from .i18n import _, _n


ArgSchema = List[Tuple[Optional[str], str, Union[None, bool, str, int]]]


PACMAN_BOOL_OPTS: ArgSchema = [
    # sync options
    ('S', 'sync', None),
    ('g', 'groups', None),
    ('i', 'info', None),
    ('w', 'downloadonly', None),
    ('q', 'quiet', None),
    ('s', 'search', None),
    ('d', 'nodeps', None),
    # query options
    ('Q', 'query', None),
    ('o', 'owns', None),
    ('l', 'list', None),  # @TODO
    # operations
    ('D', 'database', None),
    ('F', 'files', None),
    ('R', 'remove', None),
    ('T', 'deptest', None),
    ('U', 'upgrade', None),
    ('V', 'version', None),
    ('h', 'help', None),
    # universal options
    ('v', 'verbose', None),
    (None, 'noconfirm', None),
    (None, 'needed', None),
]


def get_pikaur_bool_opts() -> ArgSchema:
    return [
        (None, 'noedit', PikaurConfig().build.NoEdit.get_bool()),
        (None, 'edit', None),
        (None, 'namesonly', None),
        (None, 'repo', None),
        ('a', 'aur', None),
        (None, 'keepbuild', PikaurConfig().build.KeepBuildDir.get_bool()),
        (None, 'keepbuilddeps', PikaurConfig().build.KeepBuildDeps.get_bool()),
        (None, 'nodiff', PikaurConfig().build.NoDiff.get_bool()),
        (None, 'rebuild', None),
        (None, 'dynamic-users', PikaurConfig().build.AlwaysUseDynamicUsers.get_bool()),
        ('P', 'pkgbuild', None),
        (None, 'install', None),
        ('G', 'getpkgbuild', None),
        (None, 'deps', None),
        # undocumented options:
        (None, 'print-commands', PikaurConfig().ui.PrintCommands.get_bool()),
        (None, 'hide-build-log', None),
        (None, 'print-args-and-exit', None),
    ]


PACMAN_STR_OPTS: ArgSchema = [
    (None, 'color', None),
    ('b', 'dbpath', None),  # @TODO: pyalpm?
    ('r', 'root', None),
    (None, 'arch', None),  # @TODO
    (None, 'cachedir', None),  # @TODO
    (None, 'config', None),  # @TODO
    (None, 'gpgdir', None),
    (None, 'hookdir', None),
    (None, 'logfile', None),
    (None, 'print-format', None),  # @TODO
]


def get_pikaur_str_opts() -> ArgSchema:
    return [
        (None, 'mflags', None),
        (None, 'makepkg-config', None),
        (None, 'makepkg-path', None),
        (None, 'pikaur-config', None),
    ]


PACMAN_COUNT_OPTS: ArgSchema = [
    ('y', 'refresh', 0),
    ('u', 'sysupgrade', 0),
    ('c', 'clean', 0),
    ('k', 'check', 0),
]


def get_pikaur_count_opts() -> ArgSchema:
    return [
        (None, 'devel', 0),
    ]


PACMAN_APPEND_OPTS: ArgSchema = [
    (None, 'ignore', None),
    (None, 'ignoregroup', None),  # @TODO
    (None, 'overwrite', None),
    (None, 'assume-installed', None),  # @TODO
]


def get_pikaur_long_opts() -> List[str]:
    return [
        long_opt.replace('-', '_')
        for _short_opt, long_opt, _default in get_pikaur_bool_opts() + get_pikaur_str_opts()
    ]


def get_pacman_long_opts() -> List[str]:  # pragma: no cover
    return [
        long_opt.replace('-', '_')
        for _short_opt, long_opt, _default
        in PACMAN_BOOL_OPTS + PACMAN_STR_OPTS + PACMAN_COUNT_OPTS + PACMAN_APPEND_OPTS
    ]


class IncompatibleArguments(Exception):
    pass


class MissingArgument(Exception):
    pass


class PikaurArgs(Namespace):
    unknown_args: List[str]
    raw: List[str]
    # typehints:
    info: Optional[bool]
    nodeps: Optional[bool]
    owns: Optional[bool]
    check: Optional[bool]
    ignore: List[str]
    # positional: List[str]
    # @TODO: pylint bug:
    positional: List[str] = []

    def __getattr__(self, name: str) -> Any:
        """
        this is a hack for typing/mypy
        """
        return getattr(super(), name)

    def handle_the_same_letter(self) -> None:
        # pylint: disable=attribute-defined-outside-init,access-member-before-definition
        if self.pkgbuild and self.info:  # handle "-i"
            self.install = self.info
            self.info = False
        if (self.getpkgbuild or self.query) and self.nodeps:  # handle "-d"
            self.deps = self.nodeps
            self.nodeps = False
        if self.sync or self.pkgbuild:
            if self.owns:  # handle "-o"
                self.repo = self.owns
                self.owns = False
            if self.check:  # handle "-k"
                self.keepbuild = True
                self.check = None

    def post_process_args(self) -> None:
        # pylint: disable=attribute-defined-outside-init,access-member-before-definition
        self.handle_the_same_letter()

        new_ignore: List[str] = []
        for ignored in self.ignore or []:
            new_ignore += ignored.split(',')
        self.ignore = new_ignore

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
        result.post_process_args()
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
        if action:
            if letter and opt:
                self.add_argument(
                    '-' + letter, '--' + opt, action=action, default=default
                )
            elif opt:
                self.add_argument(
                    '--' + opt, action=action, default=default
                )
            elif letter:
                self.add_argument(
                    '-' + letter, action=action, default=default
                )
        else:
            if letter and opt:
                self.add_argument(
                    '-' + letter, '--' + opt, default=default
                )
            elif opt:
                self.add_argument(
                    '--' + opt, default=default
                )
            elif letter:
                self.add_argument(
                    '-' + letter, default=default
                )


class CachedArgs():

    args: Optional[PikaurArgs] = None


def debug_args(args: List[str], parsed_args: PikaurArgs) -> NoReturn:  # pragma: no cover
    #  pylint:disable=import-outside-toplevel
    from pprint import pprint  # pylint: disable=no-name-in-module

    print("Input:")
    print(args)
    print()
    parsed_dict = vars(parsed_args)
    pikaur_long_opts = get_pikaur_long_opts()
    pacman_long_opts = get_pacman_long_opts()
    pikaur_dict = {}
    pacman_dict = {}
    misc_args = {}
    for arg, value in parsed_dict.items():
        if arg in pikaur_long_opts:
            pikaur_dict[arg] = value
        elif arg in pacman_long_opts:
            pacman_dict[arg] = value
        else:
            misc_args[arg] = value
    print("PIKAUR parsed args:")
    pprint(pikaur_dict)
    print()
    print("PACMAN parsed args:")
    pprint(pacman_dict)
    print()
    print("MISC parsed args:")
    pprint(misc_args)
    print()
    print("Reconstructed pacman args:")
    print(reconstruct_args(parsed_args))
    print()
    print("Reconstructed pacman args without -S:")
    print(reconstruct_args(parsed_args, ignore_args=['sync']))
    sys.exit(0)


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

    for letter, opt, default in PACMAN_COUNT_OPTS + get_pikaur_count_opts():
        parser.add_letter_andor_opt(
            action='count', letter=letter, opt=opt, default=default
        )

    for letter, opt, default in PACMAN_APPEND_OPTS:
        parser.add_letter_andor_opt(
            action='append', letter=letter, opt=opt, default=default
        )

    for letter, opt, default in PACMAN_STR_OPTS + get_pikaur_str_opts():
        parser.add_letter_andor_opt(
            action=None, letter=letter, opt=opt, default=default
        )

    parser.add_argument('positional', nargs='*')

    parsed_args = parser.parse_pikaur_args(args)

    if parsed_args.positional and '-' in parsed_args.positional and not sys.stdin.isatty():
        parsed_args.positional.remove('-')
        parsed_args.positional += [
            word
            for line in sys.stdin.readlines()
            for word in line.split()
        ]

    if parsed_args.print_args_and_exit:  # pragma: no cover
        debug_args(args, parsed_args)

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
    for letter, opt, _default in (
            get_pikaur_bool_opts() + get_pikaur_str_opts() + get_pikaur_count_opts()
    ):
        if letter:
            ignore_args.append(letter)
        if opt:
            ignore_args.append(opt.replace('-', '_'))
    count_args = []
    for letter, opt, _default in PACMAN_COUNT_OPTS:
        if letter:
            count_args.append(letter)
        if opt:
            count_args.append(opt.replace('-', '_'))
    reconstructed_args = {
        f'--{key}' if len(key) > 1 else f'-{key}': value
        for key, value in vars(parsed_args).items()
        if value
        if key not in ignore_args + count_args + [
            'raw', 'unknown_args', 'positional', 'color',
            'dbpath',
            'root',
            'arch',
            'cachedir',
            'config',
            'gpgdir',
            'hookdir',
            'logfile',
            'print_format',
            'overwrite',
            'assume_installed',
            'ignoregroup',
        ]
    }
    result = list(set(
        list(reconstructed_args.keys()) + parsed_args.unknown_args
    ))
    for args_key, value in vars(parsed_args).items():
        for letter, _opt, _default in PACMAN_COUNT_OPTS:
            opt = _opt.replace('-', '_')
            if value and opt == args_key and opt not in ignore_args and letter not in ignore_args:
                result += ['--' + opt] * value
    return result


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
        ]
    print(''.join([
        pacman_help,
        '\n\n' + _('Pikaur-specific options:') + '\n' if pikaur_options_help else '',
        _format_options_help(pikaur_options_help),
    ]))
