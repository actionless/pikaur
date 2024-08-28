"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import sys
from argparse import Namespace
from pprint import pformat
from typing import TYPE_CHECKING

from .argparse_extras import ArgumentParserWithUnknowns
from .config import DECORATION, PikaurConfig
from .i18n import translate, translate_many

if TYPE_CHECKING:
    from argparse import FileType
    from collections.abc import Callable
    from typing import Any, Final, NoReturn

ArgValue = None | bool | str | int
ArgSchema = list[
    tuple[str, str, ArgValue, str | None]
    | tuple[None, str, ArgValue, str | None]
    | tuple[str, None, ArgValue, str | None]
]
PossibleArgValuesTypes = list[str] | str | bool | int | None
HelpMessage = tuple[str | None, str | None, str | None]


PACMAN_ACTIONS: "Final[ArgSchema]" = [
    ("S", "sync", None, None),
    ("Q", "query", None, None),
    ("D", "database", None, None),
    ("F", "files", None, None),
    ("R", "remove", None, None),
    ("T", "deptest", None, None),
    ("U", "upgrade", None, None),
    ("V", "version", None, None),
    ("h", "help", None, None),
]


PIKAUR_ACTIONS: "Final[ArgSchema]" = [
    ("P", "pkgbuild", None, None),
    ("G", "getpkgbuild", None, None),
    (None, "interactive_package_select", None, None),
]


ALL_PACMAN_ACTIONS: "Final[list[str]]" = [
    schema[1] for schema in PACMAN_ACTIONS
    if schema[1] is not None
]
ALL_PIKAUR_ACTIONS: "Final[list[str]]" = [
    schema[1] for schema in PIKAUR_ACTIONS
    if schema[1] is not None
]
ALL_ACTIONS: "Final[list[str]]" = ALL_PACMAN_ACTIONS + ALL_PIKAUR_ACTIONS


def print_stderr(msg: str | None = None) -> None:
    sys.stderr.write(f'{msg or ""}\n')


def pprint_stderr(msg: "Any") -> None:
    print_stderr(pformat(msg))


def print_error(message: str = "") -> None:
    print_stderr(
        " ".join((
            DECORATION,
            translate("error:"),
            message,
        )),
    )


FLAG_READ_STDIN: "Final" = "-"


class LiteralArgs:
    NOCONFIRM: "Final" = "--noconfirm"
    HELP: "Final" = "--help"


def get_pacman_bool_opts(action: str | None = None) -> ArgSchema:
    if not action:
        result = []
        for each_action in ALL_PACMAN_ACTIONS:
            result += get_pacman_bool_opts(each_action)
        return list(set(result))
    result = [
        # sync options
        ("g", "groups", None, None),
        ("w", "downloadonly", None, None),
        ("q", "quiet", False, None),
        ("s", "search", None, None),
        # universal options
        ("v", "verbose", None, None),
        (None, "debug", None, None),
        (None, "noconfirm", None, None),
        (None, "needed", False, None),
    ]
    if action == "query":
        result += [
            ("u", "upgrades", None, None),
            ("o", "owns", None, None),
        ]
    if action in {"sync", "query", "interactive_package_select"}:
        result += [
            ("l", "list", None, None),
        ]
    return result


def get_pikaur_bool_opts(action: str | None = None) -> ArgSchema:
    result = []
    if not action:
        for each_action in ALL_ACTIONS:
            result += get_pikaur_bool_opts(each_action)
        return list(set(result))
    if action in {"sync", "pkgbuild", "query", "interactive_package_select"}:
        result += [
            (
                "a", "aur", None,
                translate("query packages from AUR only"),
            ),
        ]
    if action in {"sync", "pkgbuild", "interactive_package_select"}:
        result += [
            (
                "k", "keepbuild", PikaurConfig().build.KeepBuildDir.get_bool(),
                translate("don't remove build dir after the build"),
            ),
            (
                None, "keepbuilddeps", PikaurConfig().build.KeepBuildDeps.get_bool(),
                translate("don't remove build dependencies between and after the builds"),
            ),
            (
                "o", "repo", None, translate("query packages from repository only"),
            ),
            (
                None, "noedit", PikaurConfig().review.NoEdit.get_bool(),
                translate("don't prompt to edit PKGBUILDs and other build files"),
            ),
            (
                None, "edit", None,
                translate("prompt to edit PKGBUILDs and other build files"),
            ),
            (
                None, "rebuild", None,
                translate("always rebuild AUR packages"),
            ),
            (
                None, "skip-failed-build", PikaurConfig().build.SkipFailedBuild.get_bool(),
                translate("skip failed builds"),
            ),
            (
                None, "dynamic-users", PikaurConfig().build.DynamicUsers.get_str() == "always",
                translate("always isolate with systemd dynamic users"),
            ),
            (
                None, "hide-build-log", None,
                translate("hide build log"),
            ),
            (
                None, "skip-aur-pull", None,
                translate("don't pull already cloned PKGBUILD"),
            ),
        ]
    if action in {"sync", "interactive_package_select"}:
        result += [
            (
                None, "namesonly", False,
                translate("search only in package names"),
            ),
            (
                None, "nodiff", PikaurConfig().review.NoDiff.get_bool(),
                translate("don't prompt to show the build files diff"),
            ),
            (
                None, "ignore-outofdate", PikaurConfig().sync.IgnoreOutofdateAURUpgrades.get_bool(),
                translate("ignore AUR packages' updates which marked 'outofdate'"),
            ),
        ]
    if action == "query":
        result += [
            (
                None, "repo", None,
                translate("query packages from repository only")),
        ]
    if action == "getpkgbuild":
        result += [
            (
                "d", "deps", None,
                translate("download also AUR dependencies"),
            ),
        ]
    if action == "pkgbuild":
        result += [
            (
                "i", "install", None,
                translate("install built package"),
            ),
        ]
    result += [
        (
            None, "print-commands", PikaurConfig().ui.PrintCommands.get_bool(),
            translate("print spawned by pikaur subshell commands"),
        ),
        (
            None, "pikaur-debug", None,
            translate("show only debug messages specific to pikaur"),
        ),
        # undocumented options:
        (None, "print-args-and-exit", None, None),
    ]
    return result


def get_pacman_str_opts(action: str | None = None) -> ArgSchema:
    if not action:
        result = []
        for each_action in ALL_PACMAN_ACTIONS:
            result += get_pacman_str_opts(each_action)
        return list(set(result))
    return [
        (None, "color", None, None),
        ("b", "dbpath", None, None),  # @TODO: pyalpm?
        ("r", "root", None, None),
        (None, "arch", None, None),  # @TODO
        (None, "cachedir", None, None),  # @TODO
        (None, "config", None, None),
        (None, "gpgdir", None, None),
        (None, "hookdir", None, None),
        (None, "logfile", None, None),
        (None, "print-format", None, None),  # @TODO
    ]


class ColorFlagValues:
    ALWAYS: "Final" = "always"
    NEVER: "Final" = "never"


def get_pikaur_str_opts(action: str | None = None) -> ArgSchema:
    result: ArgSchema = [
        (
            None, "home-dir",
            None,
            translate("alternative home directory location"),
        ),
        (
            None, "xdg-cache-home",
            PikaurConfig().misc.CachePath.get_str(),
            translate("alternative package cache directory location"),
        ),
        (
            None, "xdg-config-home",
            None,
            translate("alternative configuration file directory location"),
        ),
        (
            None, "xdg-data-home",
            PikaurConfig().misc.DataPath.get_str(),
            translate("alternative database directory location"),
        ),
        (
            None, "preserve-env",
            PikaurConfig().misc.PreserveEnv.get_str(),
            translate("preserve environment variables (comma-separated)"),
        ),
    ]
    if not action:
        for each_action in ALL_ACTIONS:
            result += get_pikaur_str_opts(each_action)
        return list(set(result))
    if action in {"sync", "pkgbuild", "interactive_package_select"}:
        result += [
            (
                None, "mflags",
                None,
                translate("cli args to pass to makepkg"),
            ),
            (
                None, "makepkg-config",
                None,
                translate("path to custom makepkg config"),
            ),
            (
                None, "makepkg-path",
                None,
                translate("override path to makepkg executable"),
            ),
            (
                None, "pikaur-config",
                None,
                translate("path to custom pikaur config"),
            ),
            (
                None, "build-gpgdir",
                PikaurConfig().build.GpgDir.get_str(),
                translate("set GnuPG home directory used when validating package sources"),
            ),
            (
                None, "privilege-escalation-target",
                PikaurConfig().misc.PrivilegeEscalationTarget.get_str(),
                None,
            ),
        ]
    if action == "getpkgbuild":
        result += [
            (
                "o", "output-dir",
                None,
                translate("path where to clone PKGBUILDs"),
            ),
        ]
    return result


def get_pikaur_int_opts(action: str | None = None) -> ArgSchema:
    result = []
    if not action:
        for each_action in ALL_ACTIONS:
            result += get_pikaur_int_opts(each_action)
        return list(set(result))
    if action in {"sync", "pkgbuild", "interactive_package_select"}:
        result += [
            (
                None, "aur-clone-concurrency", None,
                translate("how many git-clones/pulls to do from AUR"),
            ),
            (
                None, "user-id", PikaurConfig().misc.UserId.get_int(),
                translate("user ID to run makepkg if pikaur started from root"),
            ),
        ]
    return result


def get_pacman_count_opts(action: str | None = None) -> ArgSchema:
    if not action:
        result = []
        for each_action in ALL_PACMAN_ACTIONS:
            result += get_pacman_count_opts(each_action)
        return list(set(result))
    result = [
        ("y", "refresh", 0, None),
        ("c", "clean", 0, None),
    ]
    if action in {"sync", "interactive_package_select"}:
        result += [
            ("u", "sysupgrade", 0, None),
        ]
    if action in {"sync", "query", "interactive_package_select"}:
        result += [
            ("i", "info", 0, None),
        ]
    if action in {"database", "query"}:
        result += [
            ("k", "check", 0, None),
        ]
    if action in ALL_PACMAN_ACTIONS:
        result += [
            ("d", "nodeps", 0, None),
        ]
    return result


def get_pikaur_count_opts(action: str | None = None) -> ArgSchema:
    result = []
    if not action:
        for each_action in ALL_ACTIONS:
            result += get_pikaur_count_opts(each_action)
        return list(set(result))
    if action in {"sync", "interactive_package_select"}:
        result += [
            (
                None, "devel", 0,
                translate("always sysupgrade '-git', '-svn' and other dev packages"),
            ),
        ]
    return result


PACMAN_APPEND_OPTS: "Final[ArgSchema]" = [
    (None, "ignore", None, None),
    (None, "ignoregroup", None, None),  # @TODO
    (None, "overwrite", None, None),
    (None, "assume-installed", None, None),  # @TODO
]


ARG_DEPENDS: "Final[dict[str, dict[str, list[str]]]]" = {
    "query": {
        "upgrades": ["aur", "repo"],
    },
}

ARG_CONFLICTS: "Final[dict[str, dict[str, list[str]]]]" = {
    "sync": {
        "search": ["list", "l"],
    },
}


def get_all_pikaur_options() -> ArgSchema:
    return (
        PIKAUR_ACTIONS +
        get_pikaur_bool_opts() +
        get_pikaur_str_opts() +
        get_pikaur_count_opts() +
        get_pikaur_int_opts()
    )


def get_pikaur_long_opts() -> list[str]:
    return [
        long_opt.replace("-", "_")
        for _short_opt, long_opt, _default, _help in get_all_pikaur_options()
        if long_opt is not None
    ]


def get_pacman_long_opts() -> list[str]:  # pragma: no cover
    return [
        long_opt.replace("-", "_")
        for _short_opt, long_opt, _default, _help
        in (
            PACMAN_ACTIONS +
            get_pacman_bool_opts() +
            get_pacman_str_opts() +
            PACMAN_APPEND_OPTS +
            get_pacman_count_opts()
        )
        if long_opt is not None
    ]


class IncompatibleArgumentsError(Exception):
    pass


class MissingArgumentError(Exception):
    pass


class PikaurArgs(Namespace):
    unknown_args: list[str]
    raw: list[str]
    # typehints:
    info: bool | None
    keepbuild: bool | None
    output_dir: str | None
    # @TODO: remove? :
    # nodeps: bool | None
    # owns: bool | None
    # check: bool | None
    ignore: list[str]
    makepkg_config: str | None
    mflags: str | None
    makepkg_path: str | None
    quiet: bool
    sysupgrade: int
    devel: int
    namesonly: bool
    build_gpgdir: str
    needed: bool
    config: str | None
    refresh: int
    clean: int
    aur_clone_concurrency: int | None
    skip_aur_pull: bool | None
    positional: list[str]
    read_stdin: bool = False
    preserve_env: str = ""
    interactive_package_select: bool = False

    def __init__(self) -> None:
        self.positional = []
        super().__init__()

    def __getattr__(self, name: str) -> PossibleArgValuesTypes:
        transformed_name = name.replace("-", "_")
        result: PossibleArgValuesTypes = getattr(
            super(),
            name,
            getattr(self, transformed_name) if transformed_name in dir(self) else None,
        )
        return result

    def post_process_args(self) -> None:
        # pylint: disable=attribute-defined-outside-init
        new_ignore: list[str] = []
        for ignored in self.ignore or []:
            new_ignore += ignored.split(",")
        self.ignore = new_ignore

        if self.debug:
            self.pikaur_debug = True

        if self.pikaur_debug or self.verbose:
            self.print_commands = True

        action_found = False
        for action_name in ALL_ACTIONS:
            if getattr(self, action_name):
                action_found = True
        if not action_found and self.positional:
            self.interactive_package_select = True

    def validate(self) -> None:
        for operation, operation_depends in ARG_DEPENDS.items():  # noqa: PLR1702
            if getattr(self, operation):
                for arg_depend_on, dependant_args in operation_depends.items():
                    if not getattr(self, arg_depend_on):
                        for arg_name in dependant_args:
                            if getattr(self, arg_name):
                                raise MissingArgumentError(arg_depend_on, arg_name)
        for operation, operation_conflicts in ARG_CONFLICTS.items():  # noqa: PLR1702
            if getattr(self, operation):
                for args_conflicts, conflicting_args in operation_conflicts.items():
                    if getattr(self, args_conflicts):
                        for arg_name in conflicting_args:
                            if getattr(self, arg_name):
                                raise IncompatibleArgumentsError(args_conflicts, arg_name)

    @classmethod
    def from_namespace(
            cls,
            namespace: Namespace,
            unknown_args: list[str],
            raw_args: list[str],
    ) -> "PikaurArgs":
        result = cls()
        for key, value in namespace.__dict__.items():
            setattr(result, key, value)
        result.unknown_args = unknown_args
        if unknown_args and (result.pikaur_debug or result.debug):
            print_stderr(translate("WARNING, unknown args: {}").format(unknown_args))
        result.raw = raw_args
        result.post_process_args()
        return result

    @property
    def raw_without_pikaur_specific(self) -> list[str]:
        result = self.raw[:]
        for arg in ("--pikaur-debug", ):
            if arg in result:
                result.remove(arg)
        return result


class PikaurArgumentParser(ArgumentParserWithUnknowns):

    def error(self, message: str) -> "NoReturn":
        exc = sys.exc_info()[1]
        if exc:
            raise exc
        super().error(message)

    def parse_pikaur_args(self, raw_args: list[str]) -> PikaurArgs:
        parsed_args, unknown_args = self.parse_known_args(raw_args)
        for arg in unknown_args[:]:
            if arg.startswith("-"):
                continue
            unknown_args.remove(arg)
            parsed_args.positional.append(arg)
        return PikaurArgs.from_namespace(
            namespace=parsed_args,
            unknown_args=unknown_args,
            raw_args=raw_args,
        )

    def add_letter_andor_opt(
            self,
            action: str | None = None,
            letter: str | None = None,
            opt: str | None = None,
            default: PossibleArgValuesTypes | None = None,
            arg_type: "Callable[[str], Any] | FileType | None" = None,
    ) -> None:
        if action:
            if letter and opt:
                self.add_argument(
                    "-" + letter, "--" + opt, action=action, default=default,
                )
            elif opt:
                self.add_argument(
                    "--" + opt, action=action, default=default,
                )
            elif letter:
                self.add_argument(
                    "-" + letter, action=action, default=default,
                )
        elif arg_type:
            if letter and opt:
                self.add_argument(
                    "-" + letter, "--" + opt, default=default, type=arg_type,
                )
            elif opt:
                self.add_argument(
                    "--" + opt, default=default, type=arg_type,
                )
            elif letter:
                self.add_argument(
                    "-" + letter, default=default, type=arg_type,
                )
        else:  # noqa: PLR5501
            if letter and opt:
                self.add_argument(
                    "-" + letter, "--" + opt, default=default,
                )
            elif opt:
                self.add_argument(
                    "--" + opt, default=default,
                )
            elif letter:
                self.add_argument(
                    "-" + letter, default=default,
                )


class CachedArgs:
    args: PikaurArgs | None = None


def debug_args(args: list[str], parsed_args: PikaurArgs) -> "NoReturn":  # pragma: no cover
    print_stderr("Input:")
    pprint_stderr(args)
    print_stderr()
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
    print_stderr("PIKAUR parsed args:")
    pprint_stderr(pikaur_dict)
    print_stderr()
    print_stderr("PACMAN parsed args:")
    pprint_stderr(pacman_dict)
    print_stderr()
    print_stderr("MISC parsed args:")
    pprint_stderr(misc_args)
    print_stderr()
    print_stderr("Reconstructed pacman args:")
    pprint_stderr(reconstruct_args(parsed_args))
    print_stderr()
    print_stderr("Reconstructed pacman args without -S:")
    pprint_stderr(reconstruct_args(parsed_args, ignore_args=["sync"]))
    sys.exit(0)


def get_parser_for_action(
        app: str,
        args: list[str],
) -> tuple[PikaurArgumentParser, list[HelpMessage]]:

    parser = PikaurArgumentParser(prog=app, add_help=False)
    parser.add_argument("positional", nargs="*")
    for letter, opt, default, _help in (
            PACMAN_ACTIONS + PIKAUR_ACTIONS
    ):
        parser.add_letter_andor_opt(
            action="store_true", letter=letter, opt=opt, default=default,
        )
    parsed_action = parser.parse_pikaur_args(args)
    pikaur_action: str | None = None
    for action_name in ALL_ACTIONS:
        if getattr(parsed_action, action_name) and action_name != "help":
            pikaur_action = action_name
    if pikaur_action is None:
        return parser, []

    help_msgs: list[HelpMessage] = []
    for action_type, opt_list, is_pikaur, arg_type in (
            ("store_true", get_pacman_bool_opts(action=pikaur_action), False, None),
            ("store_true", get_pikaur_bool_opts(action=pikaur_action), True, None),
            ("count", get_pacman_count_opts(action=pikaur_action), False, None),
            ("count", get_pikaur_count_opts(action=pikaur_action), True, None),
            ("append", PACMAN_APPEND_OPTS, False, None),
            (None, get_pacman_str_opts(action=pikaur_action), False, None),
            (None, get_pikaur_str_opts(action=pikaur_action), True, None),
            (None, get_pikaur_int_opts(action=pikaur_action), True, int),
    ):
        for letter, opt, default, help_msg in opt_list:
            if arg_type:
                parser.add_letter_andor_opt(
                    action=action_type, letter=letter, opt=opt, default=default, arg_type=arg_type,
                )
            else:
                parser.add_letter_andor_opt(
                    action=action_type, letter=letter, opt=opt, default=default,
                )
            if is_pikaur:
                help_msgs.append(
                    (letter, opt, help_msg),
                )
    return parser, help_msgs


def _parse_args(args: list[str] | None = None) -> tuple[PikaurArgs, list[HelpMessage]]:
    args = args or sys.argv[1:]
    app_name = sys.argv[0] if sys.argv else "pikaur"
    parser, help_msgs = get_parser_for_action(app=app_name, args=args)
    parsed_args = parser.parse_pikaur_args(args)

    if (
            parsed_args.positional
            and FLAG_READ_STDIN in parsed_args.positional
            and not sys.stdin.isatty()
    ):
        parsed_args.positional.remove(FLAG_READ_STDIN)
        parsed_args.read_stdin = True

    if parsed_args.print_args_and_exit:  # pragma: no cover
        debug_args(args, parsed_args)

    try:
        parsed_args.validate()
    except IncompatibleArgumentsError as exc:
        print_error(
            translate("options {} can't be used together.").format(
                ", ".join([f"'--{opt}'" for opt in exc.args]),
            ),
        )
        sys.exit(1)
    except MissingArgumentError as exc:
        print_error(
            translate_many(
                "option {} can't be used without {}.",
                "options {} can't be used without {}.",
                len(exc.args[1:]),
            ).format(
                ", ".join([f"'--{opt}'" for opt in exc.args[1:]]),
                f"'--{exc.args[0]}'",
            ),
        )
        sys.exit(1)
    return parsed_args, help_msgs


def parse_args(args: list[str] | None = None) -> PikaurArgs:
    if CachedArgs.args:
        return CachedArgs.args
    parsed_args, _help = _parse_args(args=args)
    CachedArgs.args = parsed_args
    return parsed_args


def get_help() -> list[HelpMessage]:
    _parsed_args, help_msgs = _parse_args()
    return help_msgs


def reconstruct_args(parsed_args: PikaurArgs, ignore_args: list[str] | None = None) -> list[str]:
    if not ignore_args:
        ignore_args = []
    for _letter, opt, _default, _help in get_all_pikaur_options():
        # if letter:
        #     ignore_args.append(letter)
        if opt:
            ignore_args.append(opt.replace("-", "_"))
    count_args = []
    for letter, opt, _default, _help in get_pacman_count_opts():
        if letter:
            count_args.append(letter)
        if opt:
            count_args.append(opt.replace("-", "_"))
    reconstructed_args = {
        f"--{key}" if len(key) > 1 else f"-{key}": value
        for key, value in vars(parsed_args).items()
        if value
        if key not in ignore_args + count_args + [
            "raw", "unknown_args", "positional", "read_stdin",  # computed members
        ] + [
            long_arg
            for _short_arg, long_arg, default, _help in get_pacman_str_opts() + PACMAN_APPEND_OPTS
            if long_arg
        ]
    }
    result = list(set(
        list(reconstructed_args.keys()) + parsed_args.unknown_args,
    ))
    for args_key, value in vars(parsed_args).items():
        for letter, long, _default, _help in (
                get_pacman_count_opts()
        ):
            if not long:
                continue
            opt = long.replace("-", "_")
            if (
                    value
                    and (
                        opt == args_key
                    ) and (
                        opt not in ignore_args
                    ) and (
                        letter not in ignore_args
                    )
            ):
                result += ["--" + opt] * value
    return result


if __name__ == "__main__":
    parse_args()
