from pyalpm import vercmp  # pylint: disable=no-name-in-module


VERSION_SEPARATORS = ('.', '+', '-', ':')


def compare_versions(current_version, new_version):
    """
    vercmp is used to determine the relationship between two given version numbers.
    It outputs values as follows:
        < 0 : if ver1 < ver2
        = 0 : if ver1 == ver2
        > 0 : if ver1 > ver2
    """
    return vercmp(current_version, new_version)


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

    def cmp_lt(v):
        return compare_versions(v, get_version()) < 0

    def cmp_gt(v):
        return compare_versions(v, get_version()) > 0

    def cmp_eq(v):
        return compare_versions(v, get_version()) == 0

    def cmp_le(v):
        return cmp_eq(v) or cmp_lt(v)

    def cmp_ge(v):
        return cmp_eq(v) or cmp_gt(v)

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


def split_version(version):
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


def get_common_version(version1, version2):
    common_string = ''
    common_length = 0
    if '' in (version1, version2):
        return common_string, common_length
    for block1, block2 in zip(
            split_version(version1),
            split_version(version2)
    ):
        if compare_versions(block1, block2) == 0:
            common_string += block1
            if block1 not in VERSION_SEPARATORS:
                common_length += 1
        else:
            break
    return common_string, common_length


def get_version_diff(version, common_version):
    new_version_postfix = version
    if common_version != '':
        _new_version_postfix = version.split(
            common_version
        )[1:]
        new_version_postfix = common_version.join(_new_version_postfix)
    return new_version_postfix
