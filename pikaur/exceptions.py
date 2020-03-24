""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

from typing import TYPE_CHECKING, List, Optional

from .core import DataType

if TYPE_CHECKING:
    # pylint: disable=unused-import,cyclic-import
    from .build import PackageBuild  # noqa
    from .version import VersionMatcher  # noqa
    from .core import InteractiveSpawn  # noqa


class PackagesNotFound(DataType, Exception):
    packages: List[str]
    wanted_by: Optional[List[str]] = None

    def __init__(self, packages: List[str], wanted_by: Optional[List[str]] = None) -> None:
        DataType.__init__(self, packages=packages, wanted_by=wanted_by)
        message = ', '.join(packages)
        if wanted_by:
            message += f" wanted by {', '.join(wanted_by)}"
        Exception.__init__(self, message)


class PackagesNotFoundInRepo(PackagesNotFound):
    # pass
    # @TODO: pylint bug:
    packages: List[str]


class PackagesNotFoundInAUR(PackagesNotFound):
    # pass
    # @TODO: pylint bug:
    packages: List[str]


class BuildError(Exception):
    pass


class CloneError(DataType, Exception):
    build: 'PackageBuild'
    result: 'InteractiveSpawn'


class DependencyError(Exception):
    pass


class DependencyVersionMismatch(DataType, Exception):
    version_found: str
    dependency_line: str
    who_depends: str
    depends_on: str
    location: str

    version_matcher: Optional['VersionMatcher'] = None

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
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
