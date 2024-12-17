# Forked from python's stdlib argparse.ArgumentParser
# Original author: Steven J. Bethard <steven.bethard@gmail.com>.
# pylint: disable=too-many-statements,too-many-locals,too-many-branches,protected-access

import sys
from argparse import (
    PARSER,
    REMAINDER,
    SUPPRESS,
    ArgumentError,
    ArgumentParser,
    _get_action_name,  # noqa: PLC2701
)
from typing import TYPE_CHECKING

from .i18n import translate as _

if TYPE_CHECKING:
    from argparse import Action, Namespace
    from typing import Final


LONG_ARG_PREFIX: "Final" = "--"


class ArgumentParserWithUnknowns(ArgumentParser):

    def _parse_known_args(  # noqa: C901
            self,
            arg_strings: list[str],
            namespace: "Namespace",
            intermixed: bool = False,  # noqa: FBT001,FBT002
    ) -> "tuple[Namespace, list[str]]":
        # replace arg strings that are file references
        if self.fromfile_prefix_chars is not None:
            arg_strings = self._read_args_from_files(arg_strings)

        # map all mutually exclusive arguments to the other arguments
        # they can't occur with
        action_conflicts: dict[Action, list[Action]] = {}
        for mutex_group in self._mutually_exclusive_groups:
            group_actions = mutex_group._group_actions
            for i, mutex_action in enumerate(mutex_group._group_actions):
                conflicts = action_conflicts.setdefault(mutex_action, [])
                conflicts.extend(group_actions[:i])
                conflicts.extend(group_actions[i + 1:])

        # find all option indices, and determine the arg_string_pattern
        # which has an 'O' if there is an option at an index,
        # an 'A' if there is an argument, or a '-' if there is a '--'
        option_string_indices: dict[int, tuple[
            tuple[Action | None, str, str, str | None]
        ]] = {}
        arg_string_pattern_parts = []
        arg_strings_iter = iter(arg_strings)
        for i, arg_string in enumerate(arg_strings_iter):

            # all args after -- are non-options
            if arg_string == LONG_ARG_PREFIX:
                arg_string_pattern_parts.append("-")
                arg_string_pattern_parts.extend("A" for _arg_string in arg_strings_iter)

            # otherwise, add the arg to the arg strings
            # and note the index if it was an option
            else:
                option_tuples = self._parse_optional(arg_string)
                if option_tuples is None:
                    pattern = "A"
                else:
                    option_string_indices[i] = option_tuples  # type: ignore[assignment]
                    pattern = "O"
                arg_string_pattern_parts.append(pattern)

        # join the pieces together to form the pattern
        arg_strings_pattern = "".join(arg_string_pattern_parts)

        # converts arg strings to the appropriate and then takes the action
        seen_actions = set()
        seen_non_default_actions = set()
        warned = set()

        def take_action(
                action: "Action", argument_strings: list[str], option_string: str | None = None,
        ) -> None:
            seen_actions.add(action)
            argument_values = self._get_values(action, argument_strings)

            # error if this argument is not allowed with other previously
            # seen arguments
            if action.option_strings or argument_strings:
                seen_non_default_actions.add(action)
                for conflict_action in action_conflicts.get(action, []):
                    if conflict_action in seen_non_default_actions:
                        msg = _("not allowed with argument %s")
                        action_name = _get_action_name(conflict_action)
                        raise ArgumentError(action, msg % action_name)

            # take the action if we didn't receive a SUPPRESS value
            # (e.g. from a default)
            if argument_values is not SUPPRESS:
                action(self, namespace, argument_values, option_string)

        # function to convert arg_strings into an optional action
        def consume_optional(start_index: int) -> int:

            # get the optional identified at this index
            option_tuples: tuple[
                tuple[Action | None, str, str, str | None]
            ] = option_string_indices[start_index]

            # if multiple actions match, the option string was ambiguous
            if (sys.version_info >= (3, 12, 7)) and (len(option_tuples) > 1):
                options = ", ".join([
                    option_string
                    for action, option_string, sep, explicit_arg
                    in option_tuples
                ])
                args = {"option": arg_string, "matches": options}
                msg = _("ambiguous option: %(option)s could match %(matches)s")
                raise ArgumentError(None, msg % args)

            option_tuple_length_before_3_12_3 = 3
            option_tuple_length_3_12_3_onwards = 4
            option_tuple_length_3_12_7_onwards = 1

            action: Action | None
            option_string: str
            explicit_arg: str | None
            sep: str | None

            if len(option_tuples) == option_tuple_length_before_3_12_3:
                action, option_string, explicit_arg = option_tuples  # type: ignore[misc]
                sep = None
            elif len(option_tuples) == option_tuple_length_3_12_3_onwards:
                action, option_string, sep, explicit_arg = option_tuples  # type: ignore[misc]
            elif len(option_tuples) == option_tuple_length_3_12_7_onwards:
                action, option_string, sep, explicit_arg = option_tuples[0]
            else:
                raise NotImplementedError

            # identify additional optionals in the same arg string
            # (e.g. -xyz is the same as -x -y -z if no args are required)
            match_argument = self._match_argument
            action_tuples: list[tuple[Action, list[str], str]] = []
            while True:

                # if we found no optional action, skip it
                if action is None:
                    extras.append(arg_strings[start_index])
                    extras_pattern.append("O")
                    return start_index + 1

                # if there is an explicit argument, try to match the
                # optional's string arguments to only this
                if explicit_arg is not None:
                    arg_count = match_argument(action, "A")

                    # if the action is a single-dash option and takes no
                    # arguments, try to parse more single-dash options out
                    # of the tail of the option string
                    chars = self.prefix_chars
                    if (
                        arg_count == 0
                        and option_string[1] not in chars
                        and explicit_arg != ""   # noqa: PLC1901
                    ):
                        if sep or explicit_arg[0] in chars:
                            msg = _("ignored explicit argument %r")
                            raise ArgumentError(action, msg % explicit_arg)
                        action_tuples.append((action, [], option_string))
                        char = option_string[0]
                        option_string = char + explicit_arg[0]
                        optionals_map = self._option_string_actions
                        if option_string in optionals_map:
                            action = optionals_map[option_string]
                            explicit_arg = explicit_arg[1:]
                            if not explicit_arg:
                                sep = explicit_arg = None
                            elif explicit_arg[0] == "=":
                                sep = "="
                                explicit_arg = explicit_arg[1:]
                            else:
                                sep = ""
                        else:
                            # >--! CLIP-START ! ---------------------<
                            # if we encountered unknown arg
                            # return it and add later to other
                            # unknown args
                            # 2024.10.01: this is still needed with python 3.12.7
                            # 2024.12.17: this is still needed with python 3.13.1
                            # - extras.append(char + explicit_arg)
                            # - extras_pattern.append('O')
                            # - stop = start_index + 1
                            # - break
                            extras.append(option_string)
                            explicit_arg = "".join(explicit_arg[1:])
                            if explicit_arg == "":  # noqa: PLC1901
                                stop = start_index + 1
                                break
                            # >--! CLIP-END ! -----------------------<

                    # if the action expect exactly one argument, we've
                    # successfully matched the option; exit the loop
                    elif arg_count == 1:
                        stop = start_index + 1
                        args = [explicit_arg]
                        action_tuples.append((action, args, option_string))
                        break

                    # error if a double-dash option did not use the
                    # explicit argument
                    else:
                        msg = _("ignored explicit argument %r")
                        raise ArgumentError(action, msg % explicit_arg)

                # if there is no explicit argument, try to match the
                # optional's string arguments with the following strings
                # if successful, exit the loop
                else:
                    start = start_index + 1
                    selected_patterns = arg_strings_pattern[start:]
                    arg_count = match_argument(action, selected_patterns)
                    stop = start + arg_count
                    args = arg_strings[start:stop]
                    action_tuples.append((action, args, option_string))
                    break

            # add the Optional to the list and return the index at which
            # the Optional's string args stopped
            if not action_tuples:
                raise RuntimeError
            for action, args, option_string in action_tuples:
                if (  # noqa: SIM102
                    getattr(action, "deprecated", None)
                    and getattr(self, "_warning", None)
                ):
                    # @TODO: recheck with 3.13.1
                    if (
                        action.deprecated  # type: ignore[attr-defined]
                        and option_string not in warned
                    ):
                        self._warning(  # type: ignore[attr-defined]  # pylint: disable=no-member
                            _("option '%(option)s' is deprecated") %
                            {"option": option_string},
                        )
                        warned.add(option_string)
                take_action(action, args, option_string)
            return stop

        # the list of Positionals left to be parsed; this is modified
        # by consume_positionals()
        positionals = self._get_positional_actions()

        # function to convert arg_strings into positional actions
        def consume_positionals(start_index: int) -> int:
            # match as many Positionals as possible
            match_partial = self._match_arguments_partial
            selected_pattern = arg_strings_pattern[start_index:]
            arg_counts = match_partial(positionals, selected_pattern)

            # slice off the appropriate arg strings for each Positional
            # and add the Positional and its args to the list
            args: list[str] = []
            for action, arg_count in zip(positionals, arg_counts, strict=False):
                args = arg_strings[start_index: start_index + arg_count]
                # Strip out the first '--' if it is not in REMAINDER arg.
                if action.nargs == PARSER:
                    if arg_strings_pattern[start_index] == "-":
                        if args[0] != LONG_ARG_PREFIX:
                            raise RuntimeError
                        args.remove(LONG_ARG_PREFIX)
                elif action.nargs != REMAINDER and (
                    arg_strings_pattern.find("-", start_index, start_index +
                                             arg_count) >= 0
                ):
                    args.remove(LONG_ARG_PREFIX)
                start_index += arg_count
                if (  # noqa: SIM102
                    getattr(action, "deprecated", None)
                    and getattr(self, "_warning", None)
                ):
                    # @TODO: recheck with 3.13.1
                    if (
                        args
                        and action.deprecated  # type: ignore[attr-defined]
                        and action.dest not in warned
                    ):
                        self._warning(  # type: ignore[attr-defined]  # pylint: disable=no-member
                            _("argument '%(argument_name)s' is deprecated") %
                            {"argument_name": action.dest},
                        )
                        warned.add(action.dest)
                take_action(action, args)

            # slice off the Positionals that we just parsed and return the
            # index at which the Positionals' string args stopped
            positionals[:] = positionals[len(arg_counts):]
            return start_index

        # consume Positionals and Optionals alternately, until we have
        # passed the last option string
        extras: list[str] = []
        extras_pattern: list[str] = []
        start_index = 0
        max_option_string_index = max(option_string_indices) if option_string_indices else -1
        while start_index <= max_option_string_index:

            # consume any Positionals preceding the next option
            next_option_string_index = start_index
            while next_option_string_index <= max_option_string_index:
                if next_option_string_index in option_string_indices:
                    break
                next_option_string_index += 1
            if not intermixed and start_index != next_option_string_index:
                positionals_end_index = consume_positionals(start_index)

                # only try to parse the next optional if we didn't consume
                # the option string during the positionals parsing
                if positionals_end_index > start_index:
                    start_index = positionals_end_index
                    continue
                start_index = positionals_end_index

            # if we consumed all the positionals we could and we're not
            # at the index of an option string, there were extra arguments
            if start_index not in option_string_indices:
                strings = arg_strings[start_index:next_option_string_index]
                extras.extend(strings)
                extras_pattern.extend(arg_strings_pattern[start_index:next_option_string_index])
                start_index = next_option_string_index

            # consume the next optional and any arguments for it
            start_index = consume_optional(start_index)

        if not intermixed:
            # consume any positionals following the last Optional
            stop_index = consume_positionals(start_index)

            # if we didn't consume all the argument strings, there were extras
            extras.extend(arg_strings[stop_index:])
        else:
            extras.extend(arg_strings[start_index:])
            extras_pattern.extend(arg_strings_pattern[start_index:])
            joined_extras_pattern = "".join(extras_pattern)
            if len(joined_extras_pattern) != len(extras):
                raise RuntimeError
            # consume all positionals
            arg_strings = [
                s for s, c in zip(extras, joined_extras_pattern, strict=False) if c != "O"
            ]
            arg_strings_pattern = joined_extras_pattern.replace("O", "")
            stop_index = consume_positionals(0)
            # leave unknown optionals and non-consumed positionals in extras
            for i, char in enumerate(joined_extras_pattern):
                if not stop_index:
                    break
                if char != "O":
                    stop_index -= 1
                    extras[i] = None  # type: ignore[call-overload]
            extras = [s for s in extras if s is not None]

        # make sure all required actions were present and also convert
        # action defaults which were not given as arguments
        required_actions: list[str] = []
        for action in self._actions:
            if action not in seen_actions:
                if action.required and (required_action_name := _get_action_name(action)):
                    required_actions.append(required_action_name)
                elif (
                    action.default is not None and
                    isinstance(action.default, str) and
                    hasattr(namespace, action.dest) and
                    action.default is getattr(namespace, action.dest)
                ):
                    # Convert action default now instead of doing it before
                    # parsing arguments to avoid calling convert functions
                    # twice (which may fail) if the argument was given, but
                    # only if it was defined already in the namespace
                    setattr(namespace, action.dest,
                            self._get_value(action, action.default))

        if required_actions:
            raise ArgumentError(
                None,
                _("the following arguments are required: %s") % ", ".join(required_actions),
            )

        # make sure all required groups had one option present
        for group in self._mutually_exclusive_groups:
            if group.required:
                for action in group._group_actions:
                    if action in seen_non_default_actions:
                        break

                # if no actions were used, report the error
                else:
                    names = [_get_action_name(action) or "None"
                             for action in group._group_actions
                             if action.help is not SUPPRESS]
                    msg = _("one of the arguments %s is required")
                    raise ArgumentError(None, msg % " ".join(names))

        # return the updated namespace and the extra arguments
        return namespace, extras
