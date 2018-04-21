from typing import TYPE_CHECKING, List

from .core import DataType

if TYPE_CHECKING:
    # pylint: disable=unused-import
    from .build import PackageBuild  # noqa
    from .version import VersionMatcher  # noqa
    from .core import InteractiveSpawn  # noqa


class PackagesNotFoundInAUR(DataType, Exception):
    packages: List[str] = None
    wanted_by: str = None


class BuildError(Exception):
    pass


class CloneError(DataType, Exception):
    build: 'PackageBuild' = None
    result: 'InteractiveSpawn' = None


class DependencyError(Exception):
    pass


class DependencyVersionMismatch(DataType, Exception):
    version_found: str = None
    dependency_line: str = None
    who_depends: str = None
    depends_on: str = None
    location: str = None

    version_matcher: 'VersionMatcher' = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.version_matcher:
            self.dependency_line = self.version_matcher.line


class DependencyNotBuiltYet(Exception):
    pass


class AURError(Exception):
    pass


class SysExit(Exception):
    code: int = None

    def __init__(self, code: int) -> None:
        self.code = code
