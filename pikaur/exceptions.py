"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

from typing import TYPE_CHECKING

from .core import DataType, PackageSource

if TYPE_CHECKING:
    # pylint: disable=cyclic-import
    from .build import PackageBuild  # noqa
    from .version import VersionMatcher
    from .core import InteractiveSpawn


class PackagesNotFound(DataType, Exception):
    packages: list[str]
    wanted_by: list[str] | None = None

    def __init__(self, packages: list[str], wanted_by: list[str] | None = None) -> None:
        DataType.__init__(self, packages=packages, wanted_by=wanted_by)
        message = ', '.join(packages)
        if wanted_by:
            message += f" wanted by {', '.join(wanted_by)}"
        Exception.__init__(self, message)


class PackagesNotFoundInRepo(PackagesNotFound):
    # pass
    # @TODO: pylint bug:
    packages: list[str]


class PackagesNotFoundInAUR(PackagesNotFound):
    # pass
    # @TODO: pylint bug:
    packages: list[str]


class BuildError(Exception):
    pass


class CloneError(DataType, Exception):
    build: 'PackageBuild'
    result: 'InteractiveSpawn'


class DependencyError(Exception):
    pass


class DependencyVersionMismatch(DataType, Exception):
    version_found: dict[str, str] | str
    dependency_line: str
    who_depends: str
    depends_on: str
    location: PackageSource
    version_matcher: 'VersionMatcher | None' = None

    def __init__(  # pylint: disable=too-many-arguments
            self,
            version_found: dict[str, str] | str,
            dependency_line: str,
            who_depends: str,
            depends_on: str,
            location: PackageSource,
            version_matcher: 'VersionMatcher | None' = None,
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


class DependencyNotBuiltYet(Exception):
    pass


class AURError(Exception):
    url: str
    error: str

    def __init__(self, url: str, error: str) -> None:
        self.url = url
        self.error = error
        super().__init__(f"URL: {self.url}\nError: {self.error}")


class SysExit(Exception):
    code: int

    def __init__(self, code: int) -> None:
        self.code = code
        super().__init__(f"Exit code: {code}")
