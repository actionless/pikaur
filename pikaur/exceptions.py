"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

from typing import TYPE_CHECKING

from .pikatypes import DataType

if TYPE_CHECKING:
    # pylint: disable=cyclic-import
    from .build import PackageBuild
    from .pikatypes import PackageSource
    from .spawn import InteractiveSpawn
    from .version import VersionMatcher


class PackagesNotFoundError(DataType, Exception):
    packages: list[str]
    wanted_by: list[str] | None = None

    def __init__(self, packages: list[str], wanted_by: list[str] | None = None) -> None:
        DataType.__init__(self, packages=packages, wanted_by=wanted_by)
        message = ", ".join(packages)
        if wanted_by:
            message += f" wanted by {', '.join(wanted_by)}"
        Exception.__init__(self, message)


class PackagesNotFoundInRepoError(PackagesNotFoundError):
    # pass
    # @TODO: pylint bug:
    packages: list[str]


class PackagesNotFoundInAURError(PackagesNotFoundError):
    # pass
    # @TODO: pylint bug:
    packages: list[str]


class BuildError(DataType, Exception):
    message: str
    build: "PackageBuild"


class SkipBuildError(BuildError):
    pass


class CloneError(DataType, Exception):
    build: "PackageBuild"
    result: "InteractiveSpawn"


class DependencyError(Exception):
    pass


class DependencyVersionMismatchError(DataType, Exception):
    version_found: dict[str, str] | str
    dependency_line: str
    who_depends: str
    depends_on: str
    location: "PackageSource"
    version_matcher: "VersionMatcher | None" = None

    def __init__(  # noqa: PLR0917
            self,
            version_found: dict[str, str] | str,
            dependency_line: str,
            who_depends: str,
            depends_on: str,
            location: "PackageSource",
            version_matcher: "VersionMatcher | None" = None,
    ) -> None:
        super().__init__(
            version_found=version_found,
            dependency_line=dependency_line,
            who_depends=who_depends,
            depends_on=depends_on,
            location=location,
            version_matcher=version_matcher,
        )
        if self.version_matcher:
            self.dependency_line = self.version_matcher.line


class DependencyNotBuiltYetError(Exception):
    pass


class AURError(Exception):
    url: str
    error: str

    def __init__(self, url: str, error: str) -> None:
        self.url = url
        self.error = error
        super().__init__(f"URL: {self.url}\nError: {self.error}")


class SysExit(Exception):  # noqa: N818
    code: int

    def __init__(self, code: int) -> None:
        self.code = code
        super().__init__(f"Exit code: {code}")
