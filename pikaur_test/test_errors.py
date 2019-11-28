""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

# pylint: disable=no-name-in-module

from pikaur_test.helpers import PikaurDbTestCase, pikaur


MSG_CANNOT_BE_FOUND = "cannot be found"
MSG_DEPS_MISSING = "Dependencies missing"
MSG_VERSION_MISMATCH = "Version mismatch"


class FailureTest(PikaurDbTestCase):
    """
    test cases for failure situations
    """

    def test_install_not_found(self):
        """
        package can't be found in AUR
        """
        not_existing_pkg_name = "not-existing-aur-package-7h68712683h1628h1"
        result = pikaur(
            f'-S {not_existing_pkg_name}',
            capture_stderr=True
        )
        self.assertEqual(result.returncode, 6)
        self.assertIn(MSG_CANNOT_BE_FOUND, result.stderr)
        self.assertEqual(
            result.stderr.splitlines()[-1].strip(),
            not_existing_pkg_name
        )

    def test_install_not_found_repo(self):
        """
        package can't be found in AUR
        """
        not_existing_pkg_name = "not-existing-aur-package-7h68712683h1628h1"
        result = pikaur(
            f'-S {not_existing_pkg_name} --repo',
            capture_stderr=True
        )
        self.assertEqual(result.returncode, 6)
        self.assertIn(MSG_CANNOT_BE_FOUND, result.stderr)
        self.assertEqual(
            result.stderr.splitlines()[-1].strip(),
            not_existing_pkg_name
        )

    def test_dep_not_found(self):
        """
        dependency package can't be found in AUR
        """
        pkg_name = "pikaur-test-not-found-dep"
        not_existing_dep_name = "not-existing-package-y8r73ruue99y5u77t5u4r"
        result = pikaur(
            f'-Pi ./pikaur_test/PKGBUILD_not_found_dep',
            capture_stderr=True
        )
        self.assertEqual(result.returncode, 131)
        self.assertIn(MSG_DEPS_MISSING, result.stderr)
        self.assertIn(pkg_name, result.stderr)
        self.assertIn(MSG_CANNOT_BE_FOUND, result.stderr)
        self.assertEqual(
            result.stderr.splitlines()[-1].strip(),
            not_existing_dep_name
        )
        self.assertNotInstalled(pkg_name)

    def test_version_mismatch_aur(self):
        """
        dependency AUR package version not satisfied
        """
        pkg_name = "pikaur-test-version-mismatch-aur"
        result = pikaur(
            f'-Pi ./pikaur_test/PKGBUILD_version_mismatch_aur',
            capture_stderr=True
        )
        self.assertEqual(result.returncode, 131)
        self.assertIn(MSG_VERSION_MISMATCH, result.stderr)
        self.assertIn(pkg_name, result.stderr)
        self.assertNotInstalled(pkg_name)

    def test_version_mismatch_repo(self):
        """
        dependency repo package version not satisfied
        """
        pkg_name = "pikaur-test-version-mismatch-repo"
        result = pikaur(
            f'-Pi ./pikaur_test/PKGBUILD_version_mismatch_repo',
            capture_stderr=True
        )
        self.assertEqual(result.returncode, 131)
        self.assertIn(MSG_VERSION_MISMATCH, result.stderr)
        self.assertIn(pkg_name, result.stderr)
        self.assertNotInstalled(pkg_name)
