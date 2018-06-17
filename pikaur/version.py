from typing import Callable, Tuple, List, Optional

import pyalpm


VERSION_SEPARATORS = ('.', '+', '-', ':')


def compare_versions(version1: str, version2: str) -> int:
    """
    vercmp is used to determine the relationship between two given version numbers.
    It outputs values as follows:
        < 0 : if ver1 < ver2
        = 0 : if ver1 == ver2
        > 0 : if ver1 > ver2
    """
    return pyalpm.vercmp(version1, version2)


class VersionMatcher():

    version: Optional[str] = None
    version_matchers: List[Callable[[str], int]]
    depend_line: str

    def __call__(self, version: Optional[str]) -> int:
        if not version:
            return True
        return min([
            version_matcher(version)
            for version_matcher in self.version_matchers
        ])

    def __init__(self, depend_line: str) -> None:
        self.line = depend_line

        cond: Optional[str] = None
        version_matcher = self.cmp_default
        for test_cond, matcher in (
                ('>=', self.cmp_ge),
                ('<=', self.cmp_le),
                ('=', self.cmp_eq),
                ('>', self.cmp_gt),
                ('<', self.cmp_lt),
        ):
            if test_cond in depend_line:
                cond = test_cond
                version_matcher = matcher
                break

        if cond:
            self.pkg_name, self.version = depend_line.split(cond)[:2]
            # print((pkg_name, version))
        else:
            self.pkg_name = depend_line
        self.version_matchers = [version_matcher]

    def add_version_matcher(self, version_matcher: 'VersionMatcher') -> None:
        self.version_matchers.append(version_matcher.version_matchers[0])
        self.line += ',' + version_matcher.line
        if self.version:
            if version_matcher.version:
                self.version += ',' + version_matcher.version
        else:
            self.version = version_matcher.version

    def cmp_lt(self, version: str) -> int:
        if not self.version:
            return self.cmp_default(version)
        return compare_versions(version, self.version) < 0

    def cmp_gt(self, version: str) -> int:
        if not self.version:
            return self.cmp_default(version)
        return compare_versions(version, self.version) > 0

    def cmp_eq(self, version: str) -> int:
        if not self.version:
            return self.cmp_default(version)
        return compare_versions(version, self.version) == 0

    def cmp_le(self, version: str) -> int:
        return self.cmp_eq(version) or self.cmp_lt(version)

    def cmp_ge(self, version: str) -> int:
        return self.cmp_eq(version) or self.cmp_gt(version)

    def cmp_default(self, version: str) -> int:  # pylint:disable=no-self-use
        _version = version  # hello, mypy  # noqa
        return 1


# pylint: disable=invalid-name
def get_package_name_and_version_matcher_from_depend_line(
        depend_line: str
) -> Tuple[str, VersionMatcher]:
    version_matcher = VersionMatcher(depend_line)
    return version_matcher.pkg_name, version_matcher


def split_version(version: str) -> List[str]:
    splitted_version = []
    block = ''
    for char in version:
        if char in VERSION_SEPARATORS:
            splitted_version.append(block)
            splitted_version.append(char)
            block = ''
        else:
            block += char
    if block != '':
        splitted_version.append(block)
    return splitted_version


def get_common_version(version1: str, version2: str) -> Tuple[str, int]:
    common_string = ''
    common_length = 0
    if '' in (version1, version2):
        return common_string, common_length
    for block1, block2 in zip(
            split_version(version1),
            split_version(version2)
    ):
        if compare_versions(block1, block2) == 0 and block1 == block2:
            common_string += block1
            if block1 not in VERSION_SEPARATORS:
                common_length += 1
        else:
            break
    return common_string, common_length


def get_version_diff(version: str, common_version: str) -> str:
    if common_version == '':
        return version
    return common_version.join(
        version.split(common_version)[1:]
    )
