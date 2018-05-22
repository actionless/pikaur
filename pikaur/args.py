import sys
from typing import List, Any, Tuple

from . import argparse as argparse  # pylint: disable=no-name-in-module

from .i18n import _, _n
from .core import spawn
from .config import PikaurConfig
from .exceptions import MissingArgument, IncompatibleArguments


class PikaurArgs(argparse.Namespace):
    unknown_args: List[str]
    raw: List[str]

    def __getattr__(self, name: str) -> Any:
        """
        this is a hack for typing/mypy
        """
        return getattr(super(), name)

    @classmethod
    def from_namespace(
            cls,
            namespace: argparse.Namespace,
            unknown_args: List[str],
            raw_args: List[str]
    ) -> 'PikaurArgs':
        result = cls()
        for key, value in namespace.__dict__.items():
            setattr(result, key, value)
        result.unknown_args = unknown_args
        result.raw = raw_args
        return result


class PikaurArgumentParser(argparse.ArgumentParser):

    def error(self, message: str) -> None:
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

    def add_letter_andor_opt(self, action: str = None, letter: str = None, opt: str = None) -> None:
        if letter and opt:
            self.add_argument('-' + letter, '--' + opt, action=action)
        elif opt:
            self.add_argument('--' + opt, action=action)
        elif letter:
            self.add_argument('-' + letter, action=action)


PIKAUR_OPTS = (
    (None, 'noedit'),
    (None, 'edit'),
    (None, 'namesonly'),
    (None, 'repo'),
    ('a', 'aur'),
    (None, 'devel'),
    ('k', 'keepbuild'),
    (None, 'nodiff')
)


def validate_args(args: PikaurArgs) -> None:
    if args.query:
        if not args.sysupgrade:
            for arg_name in ('aur', 'repo'):
                if getattr(args, arg_name):
                    raise MissingArgument('sysupgrade', arg_name)


def parse_args(args: List[str] = None) -> PikaurArgs:
    args = args or sys.argv[1:]
    parser = PikaurArgumentParser(prog=sys.argv[0], add_help=False)

    for letter, opt in (
            ('S', 'sync'),
            ('g', 'groups'),
            ('i', 'info'),
            ('w', 'downloadonly'),
            ('q', 'quiet'),
            ('s', 'search'),
            ('u', 'sysupgrade'),
            #
            ('h', 'help'),
            ('V', 'version'),
            ('D', 'database'),
            ('F', 'files'),
            ('Q', 'query'),
            ('R', 'remove'),
            ('T', 'deptest'),
            ('U', 'upgrade'),
            #
            (None, 'noconfirm'),
            (None, 'needed'),
    ) + PIKAUR_OPTS:
        parser.add_letter_andor_opt(action='store_true', letter=letter, opt=opt)

    for letter, opt in (
            ('y', 'refresh'),
            ('c', 'clean'),
    ):
        parser.add_letter_andor_opt(action='count', letter=letter, opt=opt)

    for letter, opt in (
            (None, 'color'),
    ):
        parser.add_letter_andor_opt(action=None, letter=letter, opt=opt)

    parser.add_argument('--ignore', action='append')
    parser.add_argument('positional', nargs='*')

    parsed_args = parser.parse_pikaur_args(args)

    # print("ARGPARSE:")
    # print(parsed_args)
    # print(f'args = {args}')
    # print(unknown_args)
    # print(reconstruct_args(parsed_args))
    # print(reconstruct_args(parsed_args, ignore_args=['sync']))
    # sys.exit(0)

    try:
        validate_args(parsed_args)
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
    return parsed_args


def reconstruct_args(parsed_args: PikaurArgs, ignore_args: List[str] = None) -> List[str]:
    if not ignore_args:
        ignore_args = []
    for letter, opt in PIKAUR_OPTS:
        if letter:
            ignore_args.append(letter)
        if opt:
            ignore_args.append(opt.replace('-', '_'))
    reconstructed_args = {
        f'--{key}' if len(key) > 1 else f'-{key}': value
        for key, value in parsed_args.__dict__.items()
        if value
        if key not in ignore_args + ['raw', 'unknown_args', 'positional', 'color']
    }
    return list(set(
        list(reconstructed_args.keys()) + parsed_args.unknown_args
    ))


def cli_print_help(args: PikaurArgs) -> None:
    pikaur_long_opts = [l for s, l in PIKAUR_OPTS]
    pacman_help = spawn(
        [PikaurConfig().misc.PacmanPath, ] + reconstruct_args(args, ignore_args=pikaur_long_opts),
    ).stdout_text.replace(
        'pacman', 'pikaur'
    ).replace(
        'options:', '\n' + _("Common pacman options:")
    )
    pikaur_options_help: List[Tuple[str, str, str]] = []
    if args.sync or args.query:
        pikaur_options_help += [
            ('-a', '--aur', _("query packages from AUR only")),
            ('', '--repo', _("query packages from repository only")),
        ]
    if args.sync:
        pikaur_options_help += [
            ('', '--noedit', _("don't prompt to edit PKGBUILDs and other build files")),
            ('', '--edit', _("prompt to edit PKGBUILDs and other build files")),
            ('', '--namesonly', _("search only in package names")),
            ('', '--devel', _("always sysupgrade '-git', '-svn' and other dev packages")),
            ('-k', '--keepbuild', _("don't remove build dir after the build")),
            ('', '--nodiff', _("don't prompt to show the build files diff")),
        ]
    print(''.join([
        '\n',
        pacman_help,
        '\n\n' + _('Pikaur-specific options:') + '\n' if pikaur_options_help else '',
        '\n'.join([
            '{:>5} {:<16} {}'.format(
                short_opt and (short_opt + ',') or '', long_opt or '', descr
            )
            for short_opt, long_opt, descr in pikaur_options_help
        ])
    ]))
