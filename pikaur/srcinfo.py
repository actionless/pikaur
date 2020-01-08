""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import os
from typing import List, Dict, Optional

from .core import open_file, spawn, isolate_root_cmd, dirname
from .version import VersionMatcher
from .makepkg_config import MakepkgConfig, MakePkgCommand
from .pprint import print_stderr, print_error
from .i18n import _
from .exceptions import SysExit


class SrcInfo():

    _common_lines: List[str]
    _package_lines: List[str]
    path: str
    repo_path: str
    pkgbuild_path: str
    package_name: Optional[str]
    pkgnames: List[str]

    def load_config(self) -> None:
        self.pkgnames = []
        self._common_lines = []
        self._package_lines = []
        if not os.path.exists(self.path):
            return
        destination = self._common_lines
        with open_file(self.path) as srcinfo_file:
            for line in srcinfo_file.readlines():
                if line.startswith('pkgname ='):
                    pkgname = line.split('=')[1].strip()
                    self.pkgnames.append(pkgname)
                    if pkgname == self.package_name:
                        destination = self._package_lines
                    else:
                        destination = []
                else:
                    destination.append(line)

    def __init__(
            self,
            repo_path: str = None,
            package_name: str = None,
            pkgbuild_path: str = None
    ) -> None:
        if repo_path:
            self.repo_path = repo_path
            self.pkgbuild_path = os.path.join(repo_path, 'PKGBUILD')
        elif pkgbuild_path:
            self.pkgbuild_path = pkgbuild_path
            self.repo_path = dirname(pkgbuild_path)
        else:
            raise NotImplementedError('Either `repo_path` or `pkgbuild_path` should be set')
        self.path = os.path.join(
            self.repo_path,
            '.SRCINFO'
        )
        self.package_name = package_name
        self.load_config()

    def get_values(self, field: str, lines: List[str] = None) -> List[str]:
        prefix = field + ' = '
        values = []
        if lines is None:
            lines = self._common_lines + self._package_lines
        for line in lines:
            if line.strip().startswith(prefix):
                values.append(line.strip().split(prefix)[1])
        return values

    def get_value(self, field: str, fallback: str = None) -> Optional[str]:
        values = self.get_values(field)
        value = values[0] if values else None
        if value is None:
            value = fallback
        return value

    def get_install_script(self) -> Optional[str]:
        values = self.get_values('install')
        if values:
            return values[0]
        return None

    def _get_depends(self, field: str, lines: List[str] = None) -> Dict[str, VersionMatcher]:
        if lines is None:
            lines = self._common_lines + self._package_lines
        carch = MakepkgConfig.get('CARCH')
        dependencies: Dict[str, VersionMatcher] = {}
        for dep_line in (
                self.get_values(field, lines=lines) +
                self.get_values(f'{field}_{carch}', lines=lines)
        ):
            version_matcher = VersionMatcher(dep_line)
            pkg_name = version_matcher.pkg_name
            if pkg_name not in dependencies:
                dependencies[pkg_name] = version_matcher
            else:
                dependencies[pkg_name].add_version_matcher(version_matcher)
        return dependencies

    def _get_build_depends(self, field: str) -> Dict[str, VersionMatcher]:
        return self._get_depends(field=field, lines=self._common_lines)

    def get_depends(self) -> Dict[str, VersionMatcher]:
        return self._get_depends('depends')

    def get_build_depends(self) -> Dict[str, VersionMatcher]:
        return self._get_build_depends('depends')

    def get_build_makedepends(self) -> Dict[str, VersionMatcher]:
        return self._get_build_depends('makedepends')

    def get_build_checkdepends(self) -> Dict[str, VersionMatcher]:
        return self._get_build_depends('checkdepends')

    def get_version(self) -> str:
        epoch = self.get_value('epoch')
        version = self.get_value('pkgver')
        release = self.get_value('pkgrel')
        return '{}{}-{}'.format(
            (epoch + ':') if epoch else '',
            version,
            release
        )

    def regenerate(self) -> None:
        result = spawn(
            isolate_root_cmd(
                MakePkgCommand.get() + ['--printsrcinfo'] +
                ['-p', os.path.basename(self.pkgbuild_path)],
                cwd=self.repo_path
            ), cwd=self.repo_path
        )
        if result.returncode != 0:
            print_error(_("failed to generate .SRCINFO from {}:").format(self.pkgbuild_path))
            print_stderr(result.stderr_text)
            raise SysExit(5)
        with open_file(self.path, 'w') as srcinfo_file:
            srcinfo_file.write(result.stdout_text)
        self.load_config()
