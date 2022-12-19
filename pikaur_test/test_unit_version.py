"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
# mypy: disable-error-code=no-untyped-def

from pikaur.version import VersionMatcher
from pikaur_test.helpers import PikaurTestCase


class VersionTest(PikaurTestCase):
    """
    Inspired by:
        $ pikaur -S jdk12-openjdk
        :: error: Can't resolve dependencies for AUR package 'jdk12-openjdk':
        Version mismatch:
        jdk12-openjdk depends on: 'java-environment<=12'
         found in 'PackageSource.AUR': '12.0.2.u10-1'
    """

    def test_basic(self):
        self.assertFalse(
            VersionMatcher("=12")("12.0.2.u10-1")
        )
        self.assertFalse(
            VersionMatcher("=12.0.2.u10")("12")
        )
        self.assertFalse(
            VersionMatcher("<=12")("12.0.2.u10-1")
        )
        self.assertTrue(
            VersionMatcher("<=12.0.2.u10")("12")
        )
        self.assertFalse(
            VersionMatcher(">=12.0.2.u10")("12")
        )

    def test_pkg_deps(self):
        self.assertTrue(
            VersionMatcher("=12", is_pkg_deps=True)("12.0.2.u10-1")
        )
        self.assertFalse(
            VersionMatcher("=12.0.2.u10", is_pkg_deps=True)("12")
        )
        self.assertTrue(
            VersionMatcher("<=12", is_pkg_deps=True)("12.0.2.u10-1")
        )
        self.assertTrue(
            VersionMatcher("<=12.0.2.u10", is_pkg_deps=True)("12")
        )
        self.assertFalse(
            VersionMatcher(">=12.0.2.u10", is_pkg_deps=True)("12")
        )
