import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from .config import PikaurConfig

if TYPE_CHECKING:
    from typing import Any, Final

    import pyalpm

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

    def __eq__(self, other: object) -> bool:
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


@dataclass(eq=False)
class InstallInfo(ComparableType):
    name: str
    package: "pyalpm.Package | AURPackageInfo"
    new_version: str
    current_version: str

    description: str | None = None
    maintainer: str | None = None
    repository: str | None = None
    devel_pkg_age_days: int | None = None

    provided_by: list["pyalpm.Package | AURPackageInfo"] | None = None
    required_by: list["InstallInfo"] | None = None
    members_of: list[str] | None = None
    replaces: list[str] | None = None
    pkgbuild_path: str | None = None

    # if pkg is already installed:
    installed_as_dependency: bool | None = None
    required_by_installed: list[str] | None = None
    optional_for_installed: list[str] | None = None

    __ignore_in_eq__ = (
        "package", "provided_by", "pkgbuild_path",
        "installed_as_dependency", "required_by_installed", "optional_for_installed",
    )

    @property
    def package_source(self) -> PackageSource:
        if isinstance(self.package, AURPackageInfo):
            return PackageSource.AUR
        return PackageSource.REPO

    def __repr__(self) -> str:
        return (
            f'<{self.__class__.__name__} "{self.name}" '
            f"{self.current_version} -> {self.new_version}>"
        )


@dataclass(eq=False)
class RepoInstallInfo(InstallInfo):
    package: "pyalpm.Package"


@dataclass(eq=False)
class AURInstallInfo(InstallInfo):
    package: "AURPackageInfo"


AUR_JSON_KEY_TRANSLATIONS: "Final[dict[str, str]]" = {
    "description": "desc",
    "id": "aur_id",
    "license": "pkg_license",
}


def transform_aur_rpc_key(key: str) -> str:
    key = key.lower()
    return AUR_JSON_KEY_TRANSLATIONS.get(key, key)


@dataclass(kw_only=True)
class AURPackageInfo:  # pylint: disable=too-many-instance-attributes
    packagebase: str
    name: str
    version: str
    desc: str = ""

    numvotes: int | None = None
    popularity: float | None = None
    depends: list[str] = field(default_factory=list)
    makedepends: list[str] = field(default_factory=list)
    optdepends: list[str] = field(default_factory=list)
    checkdepends: list[str] = field(default_factory=list)
    runtimedepends: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    replaces: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)

    aur_id: int | None = None
    packagebaseid: str | None = None
    url: str | None = None
    outofdate: int | None = None
    maintainer: str | None = None
    firstsubmitted: int | None = None
    lastmodified: int | None = None
    urlpath: str | None = None
    pkg_license: str | None = None
    keywords: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    submitter: str | None = None
    comaintainers: list[str] = field(default_factory=list)

    @property
    def git_url(self) -> str:
        return f"{AurBaseUrl.get()}/{self.packagebase}.git"

    @property
    def web_url(self) -> str:
        return f"{AurBaseUrl.get()}/packages/{self.name}"

    @classmethod
    def from_srcinfo(cls, srcinfo: "SrcInfo") -> "AURPackageInfo":
        return cls(
            name=cast(str, srcinfo.package_name),
            version=(srcinfo.get_value("pkgver") or "") + "-" + (srcinfo.get_value("pkgrel") or ""),
            desc=srcinfo.get_value("pkgdesc") or "",
            packagebase=cast(str, srcinfo.get_value("pkgbase")),
            depends=[dep.line for dep in srcinfo.get_build_depends().values()],
            makedepends=[dep.line for dep in srcinfo.get_build_makedepends().values()],
            checkdepends=[dep.line for dep in srcinfo.get_build_checkdepends().values()],
            runtimedepends=[dep.line for dep in srcinfo.get_runtime_depends().values()],
            optdepends=srcinfo.get_values("optdepends"),
            conflicts=srcinfo.get_values("conflicts"),
            replaces=srcinfo.get_values("replaces"),
            provides=srcinfo.get_values("provides"),
        )

    @classmethod
    def from_json(cls, aur_json: "dict[str, Any]") -> "AURPackageInfo":
        fields = cls._get_fields()
        return cls(**{
            final_key: value
            for key, value in aur_json.items()
            if (final_key := transform_aur_rpc_key(key)) in fields
        })

    def __repr__(self) -> str:
        return (
            f'<{self.__class__.__name__} "{self.name}" '
            f"{self.version}>"
        )

    @classmethod
    def _get_fields(cls) -> set[str]:
        return set(cls.__dataclass_fields__.keys())  # pylint: disable=no-member
