"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # pylint: disable=cyclic-import
    from .build import PackageBuild
    from .pikatypes import PackageSource
    from .spawn import InteractiveSpawn
    from .version import VersionMatcher


@dataclass
class PackagesNotFoundError(Exception):
    packages: list[str]
    wanted_by: list[str] | None = None

    def __post_init__(self) -> None:
        message = ", ".join(self.packages)
        if self.wanted_by:
            message += f" wanted by {', '.join(self.wanted_by)}"
        Exception.__init__(self, message)


@dataclass
class PackagesNotFoundInRepoError(PackagesNotFoundError):
    pass


@dataclass
class PackagesNotFoundInAURError(PackagesNotFoundError):
    pass


@dataclass
class BuildError(Exception):
    message: str
    build: "PackageBuild"


@dataclass
class SkipBuildError(BuildError):
    pass


@dataclass
class CloneError(Exception):
    build: "PackageBuild"
    result: "InteractiveSpawn"


class DependencyError(Exception):
    pass


@dataclass
class DependencyVersionMismatchError(Exception):
    version_found: dict[str, str] | str
    dependency_line: str
    who_depends: str
    depends_on: str
    location: "PackageSource"
    version_matcher: "VersionMatcher | None" = None

    def __post_init__(self) -> None:
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
