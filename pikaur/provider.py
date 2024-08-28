"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

from typing import ClassVar, TypeVar, cast

import pyalpm

from .config import DECORATION
from .i18n import translate
from .pikaprint import Colors, bold_line, color_line, print_error, print_stdout
from .pikatypes import AURPackageInfo
from .print_department import print_package_search_results
from .prompt import NotANumberInputError, get_multiple_numbers_input
from .version import VersionMatcher

Package = TypeVar("Package", pyalpm.Package, AURPackageInfo)


class Provider:

    saved_providers: ClassVar[dict[str, str]] = {}

    @classmethod
    def choose(  # pylint: disable=too-many-return-statements  # noqa: PLR0911
            cls,
            dependency: str,
            options: list[Package],
            *,
            verbose: bool = False,
    ) -> Package:
        dependency_name = VersionMatcher(dependency).pkg_name
        if result := cls.saved_providers.get(dependency_name):
            for pkg in options:
                if pkg.name == result:
                    return pkg

        def rerun(*, verbose: bool = verbose) -> Package:
            return cls.choose(dependency=dependency, options=options, verbose=verbose)

        print_stdout(
            "\n"
            + color_line(f"{DECORATION} ", Colors.cyan)
            + translate("Choose a package provider for {dependency}:").format(
                dependency=bold_line(dependency),
            ),
        )
        aur_packages: list[AURPackageInfo]
        repo_packages: list[pyalpm.Package]
        if isinstance(options[0], AURPackageInfo):
            aur_packages = options
            repo_packages = []
        else:
            aur_packages = []
            repo_packages = options
        sorted_packages = cast(
            list[Package],
            print_package_search_results(
                aur_packages=aur_packages,
                repo_packages=repo_packages,
                local_pkgs_versions={},
                enumerated=True,
                list_mode=not verbose,
            ),
        )
        if not verbose:
            print_stdout(
                color_line(f"{DECORATION} ", Colors.cyan)
                + translate("[v]iew package details"),
            )

        try:
            answers = get_multiple_numbers_input(answers=list(range(len(sorted_packages))))
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
        if (answer >= len(sorted_packages)) or (answer < 0):
            print_error(translate("There are only {num} options").format(num=len(sorted_packages)))
            return rerun()
        cls.saved_providers[dependency_name] = sorted_packages[answer].name
        return sorted_packages[answer]
