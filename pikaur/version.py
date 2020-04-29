""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

from itertools import zip_longest
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
    line: str
    pkg_name: str

    def __call__(self, version: Optional[str]) -> int:
        if not version:
            return True
        return min([
            version_matcher(version)
            for version_matcher in self.version_matchers
        ])

    def __init__(self, depend_line: str) -> None:
        self.line = depend_line
        self._set_version_matcher_func()

    def add_version_matcher(self, version_matcher: 'VersionMatcher') -> None:
        if version_matcher.line in self.line.split(','):
            return
        self.version_matchers.append(version_matcher.version_matchers[0])
        self.line += ',' + version_matcher.line
        if self.version:
            if version_matcher.version:
                self.version += ',' + version_matcher.version
        else:
            self.version = version_matcher.version

    def _set_version_matcher_func(self) -> None:  # pylint: disable=too-many-locals
        # pylint: disable=invalid-name

        version: Optional[str] = None

        def get_version() -> Optional[str]:
            return version

        def cmp_lt(v: str) -> int:
            self_version = get_version()
            if not self_version:
                return cmp_default(v)
            return compare_versions(v, self_version) < 0

        def cmp_gt(v: str) -> int:
            self_version = get_version()
            if not self_version:
                return cmp_default(v)
            return compare_versions(v, self_version) > 0

        def cmp_eq(v: str) -> int:
            self_version = get_version()
            if not self_version:
                return cmp_default(v)
            return compare_versions(v, self_version) == 0

        def cmp_le(v: str) -> int:
            return cmp_eq(v) or cmp_lt(v)

        def cmp_ge(v: str) -> int:
            return cmp_eq(v) or cmp_gt(v)

        def cmp_default(v: str) -> int:
            _v = v  # hello, mypy  # noqa
            return 1

        cond: Optional[str] = None
        version_matcher = cmp_default
        for test_cond, matcher in (
                ('>=', cmp_ge),
                ('<=', cmp_le),
                ('=', cmp_eq),
                ('>', cmp_gt),
                ('<', cmp_lt),
        ):
            if test_cond in self.line:
                cond = test_cond
                version_matcher = matcher
                break

        if cond:
            splitted_line = self.line.split(cond)
            pkg_name = splitted_line[0]
            version = cond.join(splitted_line[1:])
        else:
            pkg_name = self.line

        self.pkg_name = pkg_name
        self.version = version
        self.version_matchers = [version_matcher]

    def __repr__(self) -> str:
        return (
            f'<{self.__class__.__name__} '
            f'{self.pkg_name}{[m.__name__ for m in self.version_matchers]}{self.version}>'
        )


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


def split_always(line: str, separator: str, pad_right=False) -> Tuple[str, str]:
    splitted_line = line.split(separator, 1)
    if len(splitted_line) > 1:
        return splitted_line[0], separator + splitted_line[1]
    if pad_right:
        return splitted_line[0], ''
    return '', splitted_line[0]


def rsplit_always(line: str, separator: str) -> Tuple[str, str]:
    splitted_line = line.rsplit(separator, 1)
    if len(splitted_line) > 1:
        return splitted_line[0] + separator, splitted_line[1]
    return splitted_line[0], ''


def get_common_version(version1: str, version2: str) -> Tuple[str, int]:

    def _split_epoch(version: str) -> Tuple[str, str]:
        return split_always(version, ':')

    def _split_major(version: str) -> Tuple[str, str]:
        return split_always(version, '.', pad_right=True)

    def _split_release(version: str) -> Tuple[str, str]:
        return rsplit_always(version, '-')

    common_string = ''
    diff_weight = 0
    diff_found = False
    if '' in (version1, version2):
        return common_string, diff_weight
    for weight, version_chunk1, version_chunk2 in (
            (
                1000, _split_epoch(version1)[0], _split_epoch(version2)[0]
            ),
            (
                500, _split_release(_split_major(_split_epoch(version1)[1])[0])[0],
                _split_release(_split_major(_split_epoch(version2)[1])[0])[0],
            ),
            (
                100, _split_release(_split_major(_split_epoch(version1)[1])[1])[0],
                _split_release(_split_major(_split_epoch(version2)[1])[1])[0],
            ),
            (
                10, _split_release(version1)[1], _split_release(version2)[1],
            ),
    ):
        for block1, block2 in zip_longest(
                split_version(version_chunk1),
                split_version(version_chunk2),
                fillvalue=' '
        ):
            if block1 == block2:
                if not diff_found:
                    common_string += block1
            else:
                diff_found = True
                if diff_weight == 0 and block1 not in VERSION_SEPARATORS:
                    diff_weight += weight
            weight -= 1
    return common_string, diff_weight


def get_version_diff(version: str, common_version: str) -> str:
    if common_version == '':
        return version
    return common_version.join(
        version.split(common_version)[1:]
    )
