import enum
from typing import TYPE_CHECKING

import pyalpm

from .config import PikaurConfig
from .i18n import translate
from .pikaprint import print_error

if TYPE_CHECKING:
    from typing import Any

    from .srcinfo import SrcInfo


class ComparableType:

    __ignore_in_eq__: tuple[str, ...] = ()

    __hash__ = object.__hash__
    __compare_stack__: list["ComparableType"] | None = None

    @property
    def public_values(self) -> dict[str, "Any"]:
        return {
            var: val for var, val in vars(self).items()
            if not var.startswith("__")
        }

    def __eq__(self, other: "ComparableType") -> bool:  # type: ignore[override]
        if not isinstance(other, self.__class__):
            return False
        if not self.__compare_stack__:
            self.__compare_stack__ = []
        elif other in self.__compare_stack__:
            return super().__eq__(other)
        self.__compare_stack__.append(other)
        self_values = {}
        self_values.update(self.public_values)
        others_values = {}
        others_values.update(other.public_values)
        for values in (self_values, others_values):
            for skip_prop in self.__ignore_in_eq__:
                if skip_prop in values:
                    del values[skip_prop]
        result = self_values == others_values
        self.__compare_stack__ = None
        return result


class DataType(ComparableType):

    ignore_extra_properties: bool

    @property
    def __all_annotations__(self) -> dict[str, type]:  # noqa: PLW3201
        annotations: dict[str, type] = {}
        for parent_class in reversed(self.__class__.mro()):
            annotations.update(**getattr(parent_class, "__annotations__", {}))
        return annotations

    def _key_exists(self, key: str) -> bool:
        return key in dir(self)

    def __init__(self, *, ignore_extra_properties: bool = False, **kwargs: "Any") -> None:
        self.ignore_extra_properties = ignore_extra_properties
        for key, value in kwargs.items():
            setattr(self, key, value)
        for key in self.__all_annotations__:
            if not self._key_exists(key):
                missing_required_attribute = translate(
                    "'{class_name}' does not have required attribute '{key}' set.",
                ).format(
                    class_name=self.__class__.__name__, key=key,
                )
                raise TypeError(missing_required_attribute)

    def __setattr__(self, key: str, value: "Any") -> None:
        if not (
            (
                key in self.__all_annotations__
            ) or self._key_exists(key)
        ):
            unknown_attribute = translate(
                "'{class_name}' does not have attribute '{key}' defined.",
            ).format(
                class_name=self.__class__.__name__, key=key,
            )
            if self.ignore_extra_properties:
                print_error(unknown_attribute)
            else:
                raise TypeError(unknown_attribute)
        super().__setattr__(key, value)


class AurBaseUrl:
    aur_base_url: str | None = None

    @classmethod
    def get(cls) -> str:
        if not cls.aur_base_url:
            cls.aur_base_url = PikaurConfig().network.AurUrl.get_str()
        return cls.aur_base_url


class PackageSource(enum.Enum):
    REPO = enum.auto()
    AUR = enum.auto()
    LOCAL = enum.auto()


class InstallInfo(DataType):
    name: str
    new_version: str
    description: str | None = None
    maintainer: str | None = None
    repository: str | None = None
    devel_pkg_age_days: int | None = None
    package: "pyalpm.Package | AURPackageInfo"
    provided_by: list["pyalpm.Package | AURPackageInfo"] | None = None
    required_by: list["InstallInfo"] | None = None
    members_of: list[str] | None = None
    replaces: list[str] | None = None
    pkgbuild_path: str | None = None

    # if pkg is already installed:
    current_version: str
    installed_as_dependency: bool | None = None
    required_by_installed: list[str] | None = None
    optional_for_installed: list[str] | None = None

    __ignore_in_eq__ = (
        "package", "provided_by", "pkgbuild_path",
        "installed_as_dependency", "required_by_installed", "optional_for_installed",
    )

    @property
    def package_source(self) -> PackageSource:
        if isinstance(self.package, pyalpm.Package):
            return PackageSource.REPO
        return PackageSource.AUR

    def __repr__(self) -> str:
        return (
            f'<{self.__class__.__name__} "{self.name}" '
            f"{self.current_version} -> {self.new_version}>"
        )


class RepoInstallInfo(InstallInfo):
    package: "pyalpm.Package"


class AURInstallInfo(InstallInfo):
    package: "AURPackageInfo"


class AURPackageInfo(DataType):
    packagebase: str
    name: str
    version: str
    desc: str | None = None
    numvotes: int | None = None
    popularity: float | None = None
    depends: list[str]
    makedepends: list[str]
    optdepends: list[str]
    checkdepends: list[str]
    runtimedepends: list[str]
    conflicts: list[str]
    replaces: list[str]
    provides: list[str]

    aur_id: str | None = None
    packagebaseid: str | None = None
    url: str | None = None
    outofdate: int | None = None
    maintainer: str | None = None
    firstsubmitted: int | None = None
    lastmodified: int | None = None
    urlpath: str | None = None
    pkg_license: str | None = None
    keywords: list[str]
    groups: list[str]
    submitter: str | None = None
    comaintainers: list[str]

    @property
    def git_url(self) -> str:
        return f"{AurBaseUrl.get()}/{self.packagebase}.git"

    @property
    def web_url(self) -> str:
        return f"{AurBaseUrl.get()}/packages/{self.name}"

    def __init__(self, **kwargs: "Any") -> None:
        for aur_api_name, pikaur_class_name in (
            ("description", "desc"),
            ("id", "aur_id"),
            ("license", "pkg_license"),
        ):
            if aur_api_name in kwargs:
                kwargs[pikaur_class_name] = kwargs.pop(aur_api_name)
        for key in (
            "depends",
            "makedepends",
            "optdepends",
            "checkdepends",
            "runtimedepends",
            "conflicts",
            "replaces",
            "provides",
            "keywords",
            "groups",
            "comaintainers",
        ):
            kwargs.setdefault(key, [])
        super().__init__(**kwargs)

    @classmethod
    def from_srcinfo(cls, srcinfo: "SrcInfo") -> "AURPackageInfo":
        return cls(
            name=srcinfo.package_name,
            version=(srcinfo.get_value("pkgver") or "") + "-" + (srcinfo.get_value("pkgrel") or ""),
            desc=srcinfo.get_value("pkgdesc"),
            packagebase=srcinfo.get_value("pkgbase"),
            depends=[dep.line for dep in srcinfo.get_build_depends().values()],
            makedepends=[dep.line for dep in srcinfo.get_build_makedepends().values()],
            checkdepends=[dep.line for dep in srcinfo.get_build_checkdepends().values()],
            runtimedepends=[dep.line for dep in srcinfo.get_runtime_depends().values()],
            **{
                key: srcinfo.get_values(key)
                for key in [
                    "optdepends",
                    "conflicts",
                    "replaces",
                    "provides",
                ]
            },
        )

    def __repr__(self) -> str:
        return (
            f'<{self.__class__.__name__} "{self.name}" '
            f"{self.version}>"
        )
