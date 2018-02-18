from .core import DataType


class PackagesNotFoundInAUR(DataType, Exception):
    packages = None
    wanted_by = None


class BuildError(Exception):
    pass


class CloneError(DataType, Exception):
    build = None
    result = None


class DependencyError(Exception):
    pass


class DependencyVersionMismatch(DataType, Exception):
    version_found = None
    dependency_line = None
    who_depends = None
    depends_on = None
    location = None

    version_matcher = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.version_matcher:
            self.dependency_line = self.version_matcher.line


class DependencyNotBuiltYet(Exception):
    pass
