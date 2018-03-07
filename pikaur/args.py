import sys
from typing import List

from . import argparse as argparse  # pylint: disable=no-name-in-module


class PikaurArgs(argparse.Namespace):
    unknown_args: List[str] = None
    raw: List[str] = None


class PikaurArgumentParser(argparse.ArgumentParser):

    def error(self, message: str) -> None:
        exc = sys.exc_info()[1]
        if exc:
            raise exc
        super().error(message)

    def parse_pikaur_args(self, args: List[str]) -> PikaurArgs:
        parsed_args, unknown_args = self.parse_known_args(args)
        parsed_args.unknown_args = unknown_args
        parsed_args.raw = args
        return parsed_args


PIKAUR_LONG_OPTS = (
    'noedit',
    'namesonly',
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
    ):
        parser.add_argument('-'+letter, '--'+opt, action='store_true')

    for opt in (
            'noconfirm',
            'needed',
    ) + PIKAUR_LONG_OPTS:
        parser.add_argument('--'+opt, action='store_true')

    parser.add_argument('--ignore', action='append')
    parser.add_argument('positional', nargs='*')

    parsed_args = parser.parse_pikaur_args(args)

    # print("ARGPARSE:")
    # print(parsed_args)
    # print(f'args = {args}')
    # print(reconstructed_args)
    # print(unknown_args)
    # print(reconstruct_args(parsed_args))
    # print(reconstruct_args(parsed_args, ignore_args=['sync']))
    # sys.exit(0)

    return parsed_args


def reconstruct_args(parsed_args: PikaurArgs, ignore_args: List[str]=None) -> List[str]:
    if not ignore_args:
        ignore_args = []
    ignore_args += [opt.replace('-', '_') for opt in PIKAUR_LONG_OPTS]
    reconstructed_args = {
        f'--{key}' if len(key) > 1 else f'-{key}': value
        for key, value in parsed_args.__dict__.items()
        if value
        if key not in ignore_args + ['raw', 'unknown_args', 'positional']
    }
    return list(set(
        list(reconstructed_args.keys()) + parsed_args.unknown_args
    ))
