"""Licensed under GPLv3, see https://www.gnu.org/licenses/ ."""

from itertools import zip_longest
from typing import TYPE_CHECKING

import pyalpm

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Final


VERSION_SEPARATORS: "Final" = (".", "+", "-", ":")
VERSION_DEVEL: "Final" = "devel"


def compare_versions(version1: str, version2: str) -> int:
    """
    `vercmp` is used to determine the relationship between two given version numbers.
    It outputs values as follows:
        < 0 : if ver1 < ver2
        = 0 : if ver1 == ver2
        > 0 : if ver1 > ver2
    """
    return pyalpm.vercmp(version1, version2)


class VersionMatcher:
    """
    Represents version string as stated in dependencies (e.g. `>=1.23`).
    And can match that pattern against some version.
    """

    version: str | None = None
    version_matchers: "list[Callable[[str], int]]"
    line: str
    pkg_name: str

    def __call__(self, version: str | None) -> int:
        """Check if `version` matching our `VersionMatcher`."""
        if not version:
            return True
        return min(
            version_matcher(version)
            for version_matcher in self.version_matchers
        )

    def __init__(self, depend_line: str, *, is_pkg_deps: bool = False) -> None:
        self.line = depend_line
        self._set_version_matcher_func(is_pkg_deps=is_pkg_deps)

    def add_version_matcher(self, version_matcher: "VersionMatcher") -> None:
        """
        Embed another `VersionMatcher` into this.
        So they both could check against some version
        when this `VersionMatcher` is called.
        """
        if version_matcher.line in self.line.split(","):
            return
        self.version_matchers.append(version_matcher.version_matchers[0])
        self.line += "," + version_matcher.line
        if not self.version:
            self.version = version_matcher.version
        elif version_matcher.version:
            self.version += "," + version_matcher.version

    def _set_version_matcher_func(
            self, *, is_pkg_deps: bool = False,
    ) -> None:
        # pylint: disable=invalid-name

        version: str | None = None

        def get_version() -> str | None:
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
            if is_pkg_deps:
                common_version, _ = get_common_version(v, self_version)
                if common_version == self_version:
                    return True
            return compare_versions(v, self_version) == 0

        def cmp_le(v: str) -> int:
            return cmp_eq(v) or cmp_lt(v)

        def cmp_ge(v: str) -> int:
            return cmp_eq(v) or cmp_gt(v)

        def cmp_default(v: str) -> int:  # noqa: ARG001  # pylint: disable=unused-argument
            return 1

        cond: str | None = None
        version_matcher = cmp_default
        for test_cond, matcher in (
                (">=", cmp_ge),
                ("<=", cmp_le),
                ("=", cmp_eq),
                (">", cmp_gt),
                ("<", cmp_lt),
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
            f"<{self.__class__.__name__} "
            f"{self.pkg_name}{[m.__name__ for m in self.version_matchers]}{self.version}>"
        )


def split_version(version: str) -> list[str]:
    """Split version, e.g. `"1.2+3"` to `["1", "2", "3"]`."""
    splitted_version: list[str] = []
    block = ""
    for char in version:
        if char in VERSION_SEPARATORS:
            splitted_version.extend((block, char))
            block = ""
        else:
            block += char
    if block:
        splitted_version.append(block)
    return splitted_version


def split_always(line: str, separator: str, *, pad_right: bool = False) -> tuple[str, str]:
    """
    Same as builtin string `.split()`,
    but return empty string on the left or right if no separator found.
    """
    splitted_line = line.split(separator, 1)
    if len(splitted_line) > 1:
        return splitted_line[0], separator + splitted_line[1]
    if pad_right:
        return splitted_line[0], ""
    return "", splitted_line[0]


def rsplit_always(line: str, separator: str) -> tuple[str, str]:
    """
    Same as builtin string `.rsplit()`,
    but return empty string on right if no separator found.
    """
    splitted_line = line.rsplit(separator, 1)
    if len(splitted_line) > 1:
        return splitted_line[0] + separator, splitted_line[1]
    return splitted_line[0], ""


def get_common_version(version1: str, version2: str) -> tuple[str, int]:
    """
    Get common part of two versions and compute their difference "weight".
    For example if epoch changes it affects weight by 1000,
    major version by 500 and etc.
    E.g. for `1.2.3` and `1.2.5` this would be `("1.2.", 96)`,
    for `1.2.3` and `2.0.0` - `("", 500)`.
    """

    def _split_epoch(version: str) -> tuple[str, str]:
        return split_always(version, ":")

    def _split_major(version: str) -> tuple[str, str]:
        return split_always(version, ".", pad_right=True)

    def _split_release(version: str) -> tuple[str, str]:
        return rsplit_always(version, "-")

    common_string = ""
    diff_weight = 0
    diff_found = False
    if "" in {version1, version2}:
        return common_string, diff_weight
    for initial_weight, version_chunk1, version_chunk2 in (
            (
                1000, _split_epoch(version1)[0], _split_epoch(version2)[0],
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
        weight = initial_weight
        for block1, block2 in zip_longest(
                split_version(version_chunk1),
                split_version(version_chunk2),
                fillvalue=" ",
        ):
            if block1 != block2:
                diff_found = True
                if diff_weight == 0 and block1 not in VERSION_SEPARATORS:
                    diff_weight += weight
            elif not diff_found:
                common_string += block1
            weight -= 1
    if version2 == VERSION_DEVEL:
        diff_weight = 9999
    return common_string, diff_weight


def get_version_diff(version: str, common_version: str) -> str:
    """
    Get the different part of the version and version prefix returned by `get_common_version()`.
    E.g. if version is '1.2.3' and common part - '1.2.' - the different part would be '3'.
    """
    if not common_version:
        return version
    return common_version.join(
        version.split(common_version)[1:],
    )
