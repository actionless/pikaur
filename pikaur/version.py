from distutils.version import LooseVersion


def compare_versions(current_version, new_version):
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


def compare_versions_test():
    assert compare_versions('0.2+9+123abc-1', '0.3-1')


class VersionMatcher():

    def __call__(self, version):
        result = self.version_matcher(version)
        # print(f"dep:{self.line} found:{version} result:{result}")
        return result

    def __init__(self, matcher_func, version, depend_line):
        self.version_matcher = matcher_func
        self.version = version
        self.line = depend_line


def get_package_name_from_depend_line(depend_line):  # pylint: disable=invalid-name
    # @TODO: remove this one and use next function instead
    return depend_line.split('=')[0].split('<')[0].split('>')[0]


# pylint: disable=invalid-name
def get_package_name_and_version_matcher_from_depend_line(depend_line):
    version = None

    def get_version():
        return version

    def cmp_lt(v):
        return compare_versions(v, get_version())

    def cmp_gt(v):
        return compare_versions(get_version(), v)

    def cmp_eq(v):
        return v == get_version()

    def cmp_le(v):
        return cmp_eq(v) or cmp_lt(v)

    def cmp_ge(v):
        return cmp_eq(v) or cmp_gt(v)

    cond = None
    version_matcher = lambda v: True  # noqa
    for test_cond, matcher in {
            '>=': cmp_ge,
            '<=': cmp_le,
            '=': cmp_eq,
            '>': cmp_gt,
            '<': cmp_lt,
    }.items():
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
