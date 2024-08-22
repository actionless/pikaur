"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
from typing import TYPE_CHECKING

from .args import (
    HelpMessage,
    LiteralArgs,
    get_help,
    get_pikaur_long_opts,
    parse_args,
    reconstruct_args,
)
from .config import PikaurConfig
from .i18n import PIKAUR_NAME, translate
from .pikaprint import print_stdout
from .spawn import spawn

if TYPE_CHECKING:
    from typing import Final

FIRST_COLUMN_MARGIN: "Final" = 5
FIRST_COLUMN_WIDTH: "Final" = 16


def _format_options_help(options: list[HelpMessage]) -> str:
    return "\n".join([
        "{:>{first_column_margin}} {:<{first_column_width}} {}".format(
            (short_opt and ("-" + short_opt + ",")) or "",
            (long_opt and ("--" + long_opt)) or "",
            descr if (
                (len(short_opt or "") + 1 + len(long_opt or "") + 2) < FIRST_COLUMN_WIDTH
            ) else f"\n{(FIRST_COLUMN_MARGIN + FIRST_COLUMN_WIDTH + 2) * ' '}{descr}",
            first_column_margin=FIRST_COLUMN_MARGIN,
            first_column_width=FIRST_COLUMN_WIDTH,
        )
        for short_opt, long_opt, descr in options
        if descr
    ])


def cli_print_help() -> None:
    args = parse_args()

    proc = spawn([
        PikaurConfig().misc.PacmanPath.get_str(),
        *reconstruct_args(args, ignore_args=get_pikaur_long_opts()),
    ])
    if not proc.stdout_text:
        no_response_from_pacman = translate("No response from Pacman")
        raise RuntimeError(no_response_from_pacman)
    pacman_help = proc.stdout_text.replace(
        "pacman", PIKAUR_NAME,
    ).replace(
        "options:", "\n" + translate("Common pacman options:"),
    )

    if LiteralArgs.HELP in pacman_help:
        pacman_help += (
            "\n" +
            translate("pikaur-specific operations:") + "\n    " +
            translate("pikaur {-P --pkgbuild}    [options] [file(s)]") + "\n    " +
            translate("pikaur {-G --getpkgbuild} [options] <package(s)>")
        )
    if args.pkgbuild:
        pacman_help = (
            translate("usage:  pikaur {-P --pkgbuild} [options] <file(s)>") + "\n\n" +
            translate(
                "All common pacman options as when doing `pacman -U <pkg_file>`. See `pacman -Uh`.",
            )
        )
    if args.getpkgbuild:
        pacman_help = (
            translate("usage:  pikaur {-G --getpkgbuild} [options] <package(s)>")
        )

    pikaur_options_help = get_help()

    print_stdout("".join([
        pacman_help,
        "\n\n" + translate("Pikaur-specific options:") + "\n" if pikaur_options_help else "",
        _format_options_help(pikaur_options_help),
    ]))
