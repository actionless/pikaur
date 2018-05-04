import os
from typing import List, Dict, Optional

from .core import open_file, spawn, isolate_root_cmd
from .version import get_package_name_and_version_matcher_from_depend_line, VersionMatcher
from .makepkg_config import MakepkgConfig


CARCH = MakepkgConfig.get('CARCH')


class SrcInfo():

    _common_lines: List[str]
    _package_lines: List[str]
    path: str
    repo_path: str
    package_name: Optional[str]

    def load_config(self) -> None:
        self._common_lines = []
        self._package_lines = []
        if not os.path.exists(self.path):
            return
        destination = self._common_lines
        with open_file(self.path) as srcinfo_file:
            for line in srcinfo_file.readlines():
                if line.startswith('pkgname ='):
                    if line.split('=')[1].strip() == self.package_name:
                        destination = self._package_lines
                    else:
                        destination = []
                else:
                    destination.append(line)

    def __init__(self, repo_path: str, package_name: str = None) -> None:
        self.path = os.path.join(
            repo_path,
            '.SRCINFO'
        )
        self.repo_path = repo_path
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

    def get_pkgbase_values(self, field: str) -> List[str]:
        return self.get_values(field, self._common_lines)

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

    def _get_depends(self, field: str) -> Dict[str, VersionMatcher]:
        dependencies: Dict[str, VersionMatcher] = {}
        for dep in self.get_values(field) + self.get_values(f'{field}_{CARCH}'):
            pkg_name, version_matcher = get_package_name_and_version_matcher_from_depend_line(dep)
            if pkg_name not in dependencies:
                dependencies[pkg_name] = version_matcher
            else:
                dependencies[pkg_name].add_version_matcher(version_matcher)
        return dependencies

    def get_makedepends(self) -> Dict[str, VersionMatcher]:
        return self._get_depends('makedepends')

    def get_depends(self) -> Dict[str, VersionMatcher]:
        return self._get_depends('depends')

    def get_checkdepends(self) -> Dict[str, VersionMatcher]:
        return self._get_depends('checkdepends')

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
        with open_file(self.path, 'w') as srcinfo_file:
            result = spawn(
                isolate_root_cmd(
                    ['makepkg', '--printsrcinfo'],
                    cwd=self.repo_path
                ), cwd=self.repo_path
            )
            srcinfo_file.write(result.stdout_text)
        self.load_config()
