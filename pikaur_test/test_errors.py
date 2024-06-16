"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
# mypy: disable-error-code=no-untyped-def

from typing import Final

from pikaur_test.helpers import PikaurDbTestCase, pikaur

MSG_CANNOT_BE_FOUND: Final = "cannot be found"
MSG_DEPS_MISSING: Final = "Dependencies missing"
MSG_VERSION_MISMATCH: Final = "Version mismatch"
MSG_MAKEPKG_FAILED_TO_EXECUTE: Final = "Command 'makepkg --force --nocolor' failed to execute."
MSG_FAILED_TO_BUILD_PKGS: Final = "Failed to build following packages:"


class FailureTest(PikaurDbTestCase):
    """Test cases for failure situations."""

    def test_install_not_found(self):
        """Package can't be found in AUR."""
        not_existing_pkg_name = "not-existing-aur-package-7h68712683h1628h1"
        result = pikaur(
            f"-S {not_existing_pkg_name}",
            capture_stderr=True,
        )
        self.assertEqual(result.returncode, 6)
        self.assertIn(MSG_CANNOT_BE_FOUND, result.stderr)
        self.assertEqual(
            result.stderr.splitlines()[-1].strip(),
            not_existing_pkg_name,
        )

    def test_install_not_found_repo(self):
        """Package can't be found in repo."""
        not_existing_pkg_name = "not-existing-aur-package-7h68712683h1628h1"
        result = pikaur(
            f"-S {not_existing_pkg_name} --repo",
            capture_stderr=True,
        )
        self.assertEqual(result.returncode, 6)
        self.assertIn(MSG_CANNOT_BE_FOUND, result.stderr)
        self.assertEqual(
            result.stderr.splitlines()[-1].strip(),
            not_existing_pkg_name,
        )

    def test_dep_not_found(self):
        """Dependency package can't be found in AUR."""
        pkg_name = "pikaur-test-not-found-dep"
        not_existing_dep_name = "not-existing-package-y8r73ruue99y5u77t5u4r"
        result = pikaur(
            "-Pi --noconfirm ./pikaur_test/PKGBUILD_not_found_dep",
            capture_stderr=True,
        )
        self.assertEqual(result.returncode, 125)
        self.assertIn(MSG_DEPS_MISSING, result.stderr)
        self.assertIn(pkg_name, result.stderr)
        self.assertIn(MSG_CANNOT_BE_FOUND, result.stderr)
        self.assertEqual(
            result.stderr.splitlines()[-1].strip(),
            not_existing_dep_name,
        )
        self.assertNotInstalled(pkg_name)

    def test_pkgbuild_runtime_deps_install(self):
        """Runtime dependency package can't be found in AUR."""
        pkg_name = "samplepkg_runtime_deps"
        not_existing_dep_name = "a_runtime_dependency_23478937892"
        result = pikaur(
            "-Pi --noconfirm ./pikaur_test/PKGBUILD_runtime_deps",
            capture_stderr=True,
        )
        self.assertEqual(result.returncode, 125)
        self.assertIn(MSG_DEPS_MISSING, result.stderr)
        self.assertIn(pkg_name, result.stderr)
        self.assertIn(MSG_CANNOT_BE_FOUND, result.stderr)
        self.assertEqual(
            result.stderr.splitlines()[-1].strip(),
            not_existing_dep_name,
        )
        self.assertNotInstalled(pkg_name)

    def test_version_mismatch_aur(self):
        """Dependency AUR package version not satisfied."""
        pkg_name = "pikaur-test-version-mismatch-aur"
        result = pikaur(
            "-Pi ./pikaur_test/PKGBUILD_version_mismatch_aur",
            capture_stderr=True,
        )
        self.assertEqual(result.returncode, 131)
        self.assertIn(MSG_VERSION_MISMATCH, result.stderr)
        self.assertIn(pkg_name, result.stderr)
        self.assertNotInstalled(pkg_name)

    def test_version_mismatch_repo(self):
        """Dependency repo package version not satisfied."""
        pkg_name = "pikaur-test-version-mismatch-repo"
        result = pikaur(
            "-Pi ./pikaur_test/PKGBUILD_version_mismatch_repo",
            capture_stderr=True,
        )
        self.assertEqual(result.returncode, 131)
        self.assertIn(MSG_VERSION_MISMATCH, result.stderr)
        self.assertIn(pkg_name, result.stderr)
        self.assertNotInstalled(pkg_name)

    def test_build_error(self):
        pkg_name_failed = "pikaur-test-build-error"
        pkg_name_succeeded = "pikaur-test-placeholder"
        self.remove_if_installed(pkg_name_failed, pkg_name_succeeded)
        result = pikaur(
            "-Pi"
            " --noconfirm"
            " ./pikaur_test/PKGBUILD_build_error"
            " ./pikaur_test/PKGBUILD_placeholder",
            capture_stderr=True,
        )
        self.assertEqual(result.returncode, 125)
        self.assertIn(MSG_MAKEPKG_FAILED_TO_EXECUTE, result.stderr)
        self.assertNotIn(MSG_FAILED_TO_BUILD_PKGS, result.stderr)
        self.assertIn(pkg_name_failed, result.stderr)
        self.assertNotInstalled(pkg_name_failed)
        self.assertNotInstalled(pkg_name_succeeded)

    def test_build_error_skipfailedbuild(self):
        pkg_name_failed = "pikaur-test-build-error"
        pkg_name_succeeded = "pikaur-test-placeholder"
        self.remove_if_installed(pkg_name_failed, pkg_name_succeeded)
        result = pikaur(
            "-Pi"
            " --noconfirm"
            " ./pikaur_test/PKGBUILD_build_error"
            " ./pikaur_test/PKGBUILD_placeholder"
            " --skip-failed-build",
            capture_stderr=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn(MSG_MAKEPKG_FAILED_TO_EXECUTE, result.stderr)
        self.assertIn(MSG_FAILED_TO_BUILD_PKGS, result.stderr)
        self.assertIn(pkg_name_failed, result.stderr)
        self.assertNotInstalled(pkg_name_failed)
        self.assertInstalled(pkg_name_succeeded)
