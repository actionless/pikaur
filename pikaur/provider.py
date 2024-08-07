"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

from typing import ClassVar

import pyalpm

from .aur_types import AURPackageInfo
from .i18n import translate
from .pikaprint import Colors, bold_line, color_line, print_error, print_stdout
from .print_department import print_package_search_results
from .prompt import NotANumberInputError, get_multiple_numbers_input
from .version import VersionMatcher


class Provider:

    saved_providers: ClassVar[dict[str, str]] = {}

    @classmethod
    def choose(  # pylint: disable=too-many-return-statements  # noqa: PLR0911
            cls,
            dependency: str,
            options: list[pyalpm.Package] | list[AURPackageInfo],
            *,
            verbose: bool = False,
    ) -> int:
        dependency_name = VersionMatcher(dependency).pkg_name
        if result := cls.saved_providers.get(dependency_name):
            return [pkg.name for pkg in options].index(result)

        def rerun(*, verbose: bool = verbose) -> int:
            return cls.choose(dependency=dependency, options=options, verbose=verbose)

        print_stdout(
            "\n"
            + color_line(":: ", Colors.cyan)
            + translate("Choose a package provider for {dependency}:").format(
                dependency=bold_line(dependency),
            ),
        )
        aur_packages: list[AURPackageInfo]
        repo_packages: list[pyalpm.Package]
        if isinstance(options[0], AURPackageInfo):
            aur_packages = options  # type: ignore[assignment]
            repo_packages = []
        else:
            aur_packages = []
            repo_packages = options  # type: ignore[assignment]
        print_package_search_results(
            aur_packages=aur_packages,
            repo_packages=repo_packages,
            local_pkgs_versions={},
            enumerated=True,
            list_mode=not verbose,
        )
        if not verbose:
            print_stdout(
                color_line(":: ", Colors.cyan)
                + translate("[v]iew package details"),
            )

        try:
            answers = get_multiple_numbers_input(answers=list(range(len(options))))
        except NotANumberInputError as exc:
            if exc.character == "v":
                return rerun(verbose=True)
            print_error(
                translate("Only numbers allowed, got '{character}' instead").format(
                    character=exc.character,
                ),
            )
            return rerun()
        if len(answers) > 1:
            print_error(translate("Only one answer allowed"))
            return rerun()
        if len(answers) < 1:
            return rerun()
        answer = answers[0] - 1
        if (answer >= len(options)) or (answer < 0):
            print_error(translate("There are only {num} options").format(num=len(options)))
            return rerun()
        cls.saved_providers[dependency_name] = options[answer].name
        return answer
