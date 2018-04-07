import sys
from typing import List, Any, Tuple

from . import argparse as argparse  # pylint: disable=no-name-in-module

from .i18n import _
from .core import spawn


class PikaurArgs(argparse.Namespace):
    unknown_args: List[str] = None
    raw: List[str] = None

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
        return PikaurArgs.from_namespace(
            namespace=parsed_args,
            unknown_args=unknown_args,
            raw_args=raw_args
        )


def cli_print_help(args: PikaurArgs) -> None:
    pacman_help = spawn(
        ['pacman', ] + args.raw,
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
            ('', '--namesonly', _("search only in package names")),
            ('', '--devel', _("sysupgrade '-git' and other dev packages older than 1 day")),
            ('-k', '--keepbuild', _("don't remove build dir after the build")),
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


PIKAUR_OPTS = (
    (None, 'noedit'),
    (None, 'namesonly'),
    (None, 'repo'),
    ('a', 'aur'),
    (None, 'devel'),
    ('k', 'keepbuild'),
)


def parse_args(args: List[str]) -> PikaurArgs:
    parser = PikaurArgumentParser(prog=sys.argv[0], add_help=False)

    for letter, opt in (
            ('S', 'sync'),
            ('c', 'clean'),
            ('g', 'groups'),
            ('i', 'info'),
            ('w', 'downloadonly'),
            ('q', 'quiet'),
            ('s', 'search'),
            ('u', 'sysupgrade'),
            ('y', 'refresh'),
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
        if letter and opt:
            parser.add_argument('-' + letter, '--' + opt, action='store_true')
        elif opt:
            parser.add_argument('--' + opt, action='store_true')
        elif letter:
            parser.add_argument('-' + letter, action='store_true')

    parser.add_argument('--ignore', action='append')
    parser.add_argument('positional', nargs='*')

    parsed_args = parser.parse_pikaur_args(args)

    # print("ARGPARSE:")
    # print(parsed_args)
    # print(dir(parsed_args))
    # print(f'args = {args}')
    # print(reconstructed_args)
    # print(unknown_args)
    # print(reconstruct_args(parsed_args))
    # print(reconstruct_args(parsed_args, ignore_args=['sync']))
    # sys.exit(0)

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
        if key not in ignore_args + ['raw', 'unknown_args', 'positional']
    }
    return list(set(
        list(reconstructed_args.keys()) + parsed_args.unknown_args
    ))
