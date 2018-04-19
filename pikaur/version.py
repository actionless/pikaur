from typing import Callable, Tuple, List

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

    def __call__(self, version: str) -> int:
        result = self.version_matcher(version)
        # print(f"dep:{self.line} found:{version} result:{result}")
        return result

    def __init__(self, matcher_func: Callable[[str], int], version: str, depend_line: str) -> None:
        self.version_matcher = matcher_func
        self.version = version
        self.line = depend_line


# pylint: disable=invalid-name
def get_package_name_and_version_matcher_from_depend_line(
        depend_line: str
) -> Tuple[str, VersionMatcher]:

    version: str = None

    def get_version() -> str:
        return version

    def cmp_lt(v: str) -> int:
        return compare_versions(v, get_version()) < 0

    def cmp_gt(v: str) -> int:
        return compare_versions(v, get_version()) > 0

    def cmp_eq(v: str) -> int:
        return compare_versions(v, get_version()) == 0

    def cmp_le(v: str) -> int:
        return cmp_eq(v) or cmp_lt(v)

    def cmp_ge(v: str) -> int:
        return cmp_eq(v) or cmp_gt(v)

    def cmp_default(v: str) -> int:
        _v = v  # hello, mypy  # noqa
        return 1

    cond = None
    version_matcher = cmp_default
    for test_cond, matcher in (
            ('>=', cmp_ge),
            ('<=', cmp_le),
            ('=', cmp_eq),
            ('>', cmp_gt),
            ('<', cmp_lt),
    ):
        if test_cond in depend_line:
            cond = test_cond
            version_matcher = matcher
            break

    if cond:
        pkg_name, version = depend_line.split(cond)[:2]
        # print((pkg_name, version))
    else:
        pkg_name = depend_line

    return pkg_name, VersionMatcher(version_matcher, version, depend_line)


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
