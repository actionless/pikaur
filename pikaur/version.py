from pyalpm import vercmp  # pylint: disable=no-name-in-module


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
