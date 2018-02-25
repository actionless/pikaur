from distutils.version import LooseVersion
import ctypes
import re
from itertools import zip_longest


class PackageVersion:
    VERSION_RE = re.compile(r'''
        ((?P<epoch>\d*):)? # epoch?
        (?P<pkgver>[^-]+)  # pkgver
        (-(?P<pkgrel>.*))?   # pkgrel?
        $
    ''', re.VERBOSE)

    PKGVER_PART_RE = re.compile(r'(\d+)|([a-zA-Z]+)')

    def __init__(self, version_string):
        self.version_string = version_string

        match = self.VERSION_RE.match(version_string)
        epoch = match.group('epoch')
        if not epoch:
            epoch = 0
        else:
            epoch = int(epoch)

        self.epoch = epoch
        self.pkgver = match.group('pkgver')
        self.pkgrel = match.group('pkgrel')

        if self.pkgrel == '':
            self.pkgrel = None

        self.pkgver_span = match.span('pkgver')

        self.pkgver_parts = self._get_pkgver_parts(self.pkgver, offset=self.pkgver_span[0])


    def _get_pkgver_parts(self, pkgver, offset):
        parts = []
        for match in self.PKGVER_PART_RE.finditer(pkgver):
            if match[1] != None:
                part = int(match[1])
            else:
                part = match[2]

            span = match.span()
            parts.append((part, (offset + span[0], offset + span[1])))

        return parts

    # pylint: disable=too-many-return-statements
    def compare(self, other):
        '''
        Returns a pair consisting of:
        - Either -1, 0 or 1 indicating self < / = / > other.
        - The first index of self's version string where the two fail to match.
          If the two compare equal this is the length of the string.
        '''

        def unequal_res(ver1, ver2, pos):
            return (-1 if ver1 < ver2 else 1, pos)

        prefix = 0
        if self.epoch != other.epoch:
            return unequal_res(self.epoch, other.epoch, prefix)

        prefix = self.pkgver_span[0]

        # Remove :
        if prefix != 0:
            prefix -= 1

        for part_span1, part_span2 in zip_longest(self.pkgver_parts, other.pkgver_parts):
            if part_span1 is None:
                return (-1, self.pkgver_span[1])

            part1, span1 = part_span1

            if part_span2 is None:
                return (1, prefix)

            part2, _ = part_span2

            if part1 == part2:
                prefix = span1[1]
                continue

            int1 = isinstance(part1, int)
            int2 = isinstance(part2, int)

            if int1 and int2:
                return unequal_res(part1, part2, prefix)
            elif int1:
                return (1, prefix)
            elif int2:
                return (-1, prefix)

            return unequal_res(part1, part2, prefix)

        if self.pkgrel == other.pkgrel or None in (self.pkgrel, other.pkgrel):
            return (0, len(self.version_string))

        return unequal_res(self.pkgrel, other.pkgrel, self.pkgver_span[1])


    def __eq__(self, other):
        return self.compare(other)[0] == 0

    def __lt__(self, other):
        return self.compare(other)[0] == -1

    def __gt__(self, other):
        return self.compare(other)[0] == 1

    def __le__(self, other):
        return self.compare(other)[0] <= 0

    def __ge__(self, other):
        return self.compare(other)[0] >= 0

    def __str__(self):
        return self.version_string


def compare_versions_bak(current_version, new_version):
    # @TODO: remove this before the release
    if current_version != new_version:
        for separator in ('+',):
            current_version = current_version.replace(separator, '.')
            new_version = new_version.replace(separator, '.')
        current_base_version = new_base_version = None
        for separator in (':',):
            if separator in current_version:
                current_base_version, _current_version = \
                    current_version.split(separator)[:2]
            if separator in new_version:
                new_base_version, _new_version = \
                    new_version.split(separator)[:2]
            if (
                    current_base_version and new_base_version
            ) and (
                current_base_version != new_base_version
            ):
                current_version = current_base_version
                new_version = new_base_version
                break

        versions = [current_version, new_version]
        try:
            versions.sort(key=LooseVersion)
        except TypeError:
            # print(versions)
            return False
        return versions[1] == new_version
    return False


_CACHED_VERSION_COMPARISONS = {}


def compare_versions(current_version, new_version):
    """
    vercmp is used to determine the relationship between two given version numbers.
    It outputs values as follows:
        < 0 : if ver1 < ver2
        = 0 : if ver1 == ver2
        > 0 : if ver1 > ver2
    """
    if current_version == new_version:
        return 0
    if not _CACHED_VERSION_COMPARISONS.setdefault(current_version, {}).get(new_version):
        libalpm = ctypes.cdll.LoadLibrary('libalpm.so')
        compare_result = libalpm.alpm_pkg_vercmp(
            bytes(current_version, 'ascii'), bytes(new_version, 'ascii')
        )
        _CACHED_VERSION_COMPARISONS[current_version][new_version] = compare_result
    return _CACHED_VERSION_COMPARISONS[current_version][new_version]


def compare_versions_test():
    for expected_result, old_version, new_version, *prefixes in (
            (-1, '0.2+9+123abc-1', '0.3-1', '0', '0'),
            (-1, '0.50.12', '0.50.13', '0.50', '0.50'),
            (-1, '0.50.19', '0.50.20', '0.50', '0.50'),
            (-1, '0.50.2-1', '0.50.2+6+123131-1', '0.50.2', '0.50.2'),
            (-1, '0.50.2+1', '0.50.2+6+123131-1', '0.50.2', '0.50.2'),
            (0, '0.50.1', '0.50.1'),
            (0, '0:1.2.3', '1.2.3'),
            (0, ':1.2.3', '1.2.3'),
            (0, '1.2.3', '1.2.3-1'),
            (0, '1.2.3', '1.2.3-7'),
            (0, '1.2.3', '1.2.3-'),
            (-1, '1.2.3-1', '1.2.3-7', '1.2.3', '1.2.3'),
            (-1, '11.2.3', '1:1.2.3', '', ''),
            (0, '1.2.3', '1.02.0003'),
            (-1, '1.2.3', '1.02.004', '1.2', '1.02'),
            (0, '1+2', '1.2'),
    ):
        res = compare_versions_bak(old_version, new_version)
        if res != (expected_result < 0):
            print(f'compare_versions_bak failed: cmp({old_version}, {new_version})'
                  f' should be {expected_result}, not {-1 if res else 0}')

        res1, prefix1 = PackageVersion(old_version).compare(PackageVersion(new_version))
        res2, prefix2 = PackageVersion(new_version).compare(PackageVersion(old_version))

        if res1 != -res2:
            print(f'PackageVersion compare arguments are not swappable:'
                  f'{old_version}, {new_version}')

        if expected_result != 0:
            expected1 = prefixes[0]
            expected2 = prefixes[1]
        else:
            expected1 = old_version
            expected2 = new_version

        if old_version[:prefix1] != expected1:
            print(f'PackageVersion prefix is wrong ({old_version}, {new_version}):'
                  f'got {old_version[:prefix1]}, expected {expected1}')

        if new_version[:prefix2] != expected2:
            print(f'PackageVersion prefix is wrong ({new_version}, {old_version}):'
                  f'got {new_version[:prefix2]}, expected {expected2}')

        if res1 != expected_result:
            print(f'PackageVersion compare failed: cmp({old_version}, {new_version})'
                  f'should be {expected_result}, not {res1}')
        assert compare_versions(old_version, new_version) == expected_result

    print("Tests passed!")


class VersionMatcher():

    def __call__(self, version):
        result = self.version_matcher(version)
        # print(f"dep:{self.line} found:{version} result:{result}")
        return result

    def __init__(self, matcher_func, version, depend_line):
        self.version_matcher = matcher_func
        self.version = version
        self.line = depend_line


# pylint: disable=invalid-name
def get_package_name_and_version_matcher_from_depend_line(depend_line):
    version = None

    def get_version():
        return version

    def _cmp(v):
        return compare_versions(v, get_version())

    def cmp_lt(v):
        return _cmp(v) < 0

    def cmp_gt(v):
        return _cmp(v) > 0

    def cmp_eq(v):
        return _cmp(v) == 0

    def cmp_le(v):
        return _cmp(v) <= 0

    def cmp_ge(v):
        return _cmp(v) >= 0

    cond = None
    version_matcher = lambda v: True  # noqa
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
