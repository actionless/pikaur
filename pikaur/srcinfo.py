"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import shutil
from pathlib import Path

from .config import BuildCachePath, CacheRoot, UsingDynamicUsers
from .exceptions import SysExit
from .i18n import translate
from .makepkg_config import MakePkgCommand, MakepkgConfig
from .os_utils import chown_to_current, open_file
from .pikaprint import print_error, print_stderr
from .privilege import isolate_root_cmd
from .spawn import spawn
from .version import VersionMatcher


class SrcInfo:

    _common_lines: list[str]
    _package_lines: list[str]
    path: Path
    repo_path: Path
    pkgbuild_path: Path
    package_name: str | None
    pkgnames: list[str]

    def load_config(self) -> None:
        self.pkgnames = []
        self._common_lines = []
        self._package_lines = []
        if not self.path.exists():
            return
        destination = self._common_lines
        with open_file(self.path) as srcinfo_file:
            for line in srcinfo_file.readlines():
                if line.startswith("pkgname ="):
                    pkgname = line.split("=")[1].strip()
                    self.pkgnames.append(pkgname)
                    destination = self._package_lines if pkgname == self.package_name else []
                else:
                    destination.append(line)

    def __init__(
            self,
            repo_path: str | Path | None = None,
            package_name: str | None = None,
            pkgbuild_path: str | Path | None = None,
    ) -> None:
        if repo_path:
            self.repo_path = Path(repo_path)
            self.pkgbuild_path = self.repo_path / "PKGBUILD"
        elif pkgbuild_path:
            self.pkgbuild_path = Path(pkgbuild_path)
            self.repo_path = self.pkgbuild_path.parent
        else:
            missing_property_error = translate(
                "Either `{prop1}` or `{prop2}` should be set",
            ).format(
                prop1="repo_path",
                prop2="pkgbuild_path",
            )
            raise NotImplementedError(missing_property_error)
        self.path = self.repo_path / ".SRCINFO"
        self.package_name = package_name
        self.load_config()

    def get_values(self, field: str, lines: list[str] | None = None) -> list[str]:
        prefix = field + " = "
        if lines is None:
            lines = self._common_lines + self._package_lines
        return [
            line.strip().split(prefix)[1]
            for line in lines
            if line.strip().startswith(prefix)
        ]

    def get_value(self, field: str, fallback: str | None = None) -> str | None:
        values = self.get_values(field)
        value = values[0] if values else None
        if value is None:
            return fallback
        return value

    def get_install_script(self) -> str | None:
        values = self.get_values("install")
        if values:
            return values[0]
        return None

    def _get_depends(self, field: str, lines: list[str] | None = None) -> dict[str, VersionMatcher]:
        if lines is None:
            lines = self._common_lines + self._package_lines
        carch = MakepkgConfig.get("CARCH")
        dependencies: dict[str, VersionMatcher] = {}
        for dep_line in (
                self.get_values(field, lines=lines) +
                self.get_values(f"{field}_{carch}", lines=lines)
        ):
            version_matcher = VersionMatcher(dep_line, is_pkg_deps=True)
            pkg_name = version_matcher.pkg_name
            if pkg_name not in dependencies:
                dependencies[pkg_name] = version_matcher
            else:
                dependencies[pkg_name].add_version_matcher(version_matcher)
        return dependencies

    def _get_build_depends(self, field: str) -> dict[str, VersionMatcher]:
        return self._get_depends(field=field, lines=self._common_lines)

    def get_runtime_depends(self) -> dict[str, VersionMatcher]:
        return self._get_depends("depends")

    def get_build_depends(self) -> dict[str, VersionMatcher]:
        return self._get_build_depends("depends")

    def get_build_makedepends(self) -> dict[str, VersionMatcher]:
        return self._get_build_depends("makedepends")

    def get_build_checkdepends(self) -> dict[str, VersionMatcher]:
        return self._get_build_depends("checkdepends")

    def get_version(self) -> str:
        epoch = self.get_value("epoch")
        epoch_display = (epoch + ":") if epoch else ""
        version = self.get_value("pkgver")
        release = self.get_value("pkgrel")
        return f"{epoch_display}{version}-{release}"

    def regenerate(self) -> None:
        working_directory = self.repo_path
        if UsingDynamicUsers() and not str(self.repo_path).startswith(str(CacheRoot())):
            working_directory = BuildCachePath() / (
                "_info_" + (self.get_value("pkgbase") or "unknown")
            )
            if not working_directory.exists():
                working_directory.mkdir()
            shutil.copy(self.pkgbuild_path, working_directory)
        result = spawn(
            isolate_root_cmd(
                [
                    *MakePkgCommand.get(),
                    "--printsrcinfo",
                    "-p", self.pkgbuild_path.name,
                ],
                cwd=working_directory,
            ),
            cwd=working_directory,
        )
        if result.returncode != 0 or not result.stdout_text:
            print_error(
                translate("failed to generate .SRCINFO from {}:").format(self.pkgbuild_path),
            )
            print_stderr(result.stderr_text)
            raise SysExit(5)
        with open_file(self.path, "w") as srcinfo_file:
            srcinfo_file.write(result.stdout_text)
        chown_to_current(self.path)
        self.load_config()
