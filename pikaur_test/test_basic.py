"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
# mypy: disable-error-code=no-untyped-def
# pylint: disable=invalid-name

import os
import tempfile

from pikaur_test.helpers import PikaurDbTestCase, fake_pikaur, pikaur, spawn


class InstallTest(PikaurDbTestCase):
    """Basic installation cases."""

    def test_aur_package_with_repo_deps(self):
        # aur package with repo deps
        pikaur("-S python-pygobject-stubs")
        self.assertInstalled("python-pygobject-stubs")

    def test_repo_package_wo_deps(self):
        # repo package w/o deps
        pikaur("-S nano")
        self.assertInstalled("nano")

    def test_repo_package_with_deps(self):
        # repo package with deps
        pikaur("-S flac")
        self.assertInstalled("flac")

    def test_aur_package_with_aur_dep(self):
        # pikaur -Qi (pikaur -Qdmq) | grep -i -e Name -e 'Required By' -e '^$'
        # pkg_name = "python-gaphor"
        # dep_name = "python-generic"
        pkg_name = "python-guessit"
        dep_name = "python-rebulk"
        self.remove_if_installed(pkg_name, dep_name)

        pikaur(f"-S {pkg_name} --mflags=--skippgpcheck")
        self.assertInstalled(pkg_name)
        self.assertInstalled(dep_name)

        # package removal (pacman wrapping test)
        pikaur(f"-Rs {pkg_name} {dep_name} --noconfirm")
        self.assertNotInstalled(pkg_name)
        self.assertNotInstalled(dep_name)

    def test_aur_package_with_alternative_aur_dep(self):
        pkg_name = "dwm"
        dep_name = "st"
        dep_alt_name = "st-git"
        self.remove_if_installed(pkg_name, dep_name, dep_alt_name)

        # aur package with manually chosen aur dep:
        pikaur(f"-S {pkg_name} {dep_alt_name}")
        self.assertInstalled(pkg_name)
        self.assertProvidedBy(dep_name, dep_alt_name)
        self.assertInstalled(dep_alt_name)
        self.assertNotInstalled(dep_name)

    def test_aur_pkg_with_already_installed_alternative_aur_dep(self):
        pkg_name = "dwm"
        dep_name = "st"
        dep_alt_name = "st-git"
        self.remove_if_installed(pkg_name, dep_name, dep_alt_name)

        pikaur(f"-S {dep_alt_name} --mflags=--skippgpcheck")
        self.assertInstalled(dep_alt_name)
        self.assertProvidedBy(dep_name, dep_alt_name)
        self.assertInstalled(dep_alt_name)
        self.assertNotInstalled(dep_name)

        # aur package with aur dep provided by another already installed AUR pkg
        pikaur(f"-S {pkg_name}")
        self.assertInstalled(pkg_name)

    def test_pkgbuild(self):
        pkg_name = "pikaur-git"

        pikaur(f"-R --noconfirm {pkg_name}")
        self.assertNotInstalled(pkg_name)

        pikaur("-P ./PKGBUILD --noconfirm --install")
        self.assertInstalled(pkg_name)

        pikaur(f"-R --noconfirm {pkg_name}")
        self.assertNotInstalled(pkg_name)

        pikaur("-P --noconfirm --install")
        self.assertInstalled(pkg_name)

    def test_pkgbuild_runtime_deps(self):
        pkg_name = "samplepkg_runtime_deps"
        result = pikaur(
            "-P ./pikaur_test/PKGBUILD_runtime_deps",
            capture_stderr=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertNotInstalled(pkg_name)

    def test_pkgbuild_split_packages(self):
        # pkg_base = "lua-xmlrpc"
        pkg_name1 = "lua51-xmlrpc"
        pkg_name2 = "lua52-xmlrpc"

        self.remove_if_installed(pkg_name1)
        self.remove_if_installed(pkg_name2)

        pikaur(f"-G {pkg_name1}")
        fake_pikaur(f"-P ./{pkg_name1}/PKGBUILD --noconfirm --install --mflags=--skippgpcheck")
        self.assertInstalled(pkg_name1)
        self.assertInstalled(pkg_name2)

    def test_pkgbuild_custom_gpgdir(self):
        pkg_name = "zfs-utils"
        pkg_keys = [
            "4F3BA9AB6D1F8D683DC2DFB56AD860EED4598027",
            "C33DF142657ED1F7C328A2960AB9E991C6AF658B",
        ]
        keyserver = "hkp://keyserver.ubuntu.com:11371"

        with tempfile.TemporaryDirectory() as tmpdirname:
            env = {**os.environ, "GNUPGHOME": tmpdirname}
            commands = [
                "gpg --batch --passphrase  --quick-generate-key 'pikaur@localhost' rsa sign 0",
                *[f"gpg --keyserver {keyserver} --receive-keys {key}" for key in pkg_keys],
                *[f"gpg --quick-lsign-key {key}" for key in pkg_keys],
                f"chmod 755 {tmpdirname}",
                f"chmod 644 {tmpdirname}/pubring.gpg",
                f"chmod 644 {tmpdirname}/trust.gpg",
            ]

            for command in commands:
                spawn(command, env=env)

            fake_pikaur(f"--build-gpgdir {tmpdirname} -S {pkg_name}")
            self.assertInstalled(pkg_name)

        # Cleanup to ensure no impact on other tests
        self.remove_if_installed(pkg_name)

    def test_conflicting_aur_packages(self):
        conflicting_aur_package1 = "2bwm"
        conflicting_aur_package2 = "2bwm-git"
        self.remove_if_installed(
            conflicting_aur_package1,
            conflicting_aur_package2,
        )
        self.assertEqual(
            pikaur(
                f"-S {conflicting_aur_package1}"
                f" {conflicting_aur_package2}",
            ).returncode, 131,
        )
        self.assertNotInstalled(conflicting_aur_package1)
        self.assertNotInstalled(conflicting_aur_package2)

    def test_conflicting_aur_and_repo_packages(self):
        self.remove_if_installed("abduco", "abduco-git")
        self.assertEqual(
            pikaur("-S abduco-git abduco").returncode, 131,
        )
        self.assertNotInstalled("abduco")
        self.assertNotInstalled("abduco-git")

    def test_conflicting_aur_and_installed_repo_packages(self):
        self.remove_if_installed("abduco", "abduco-git")
        self.assertEqual(
            pikaur("-S abduco").returncode, 0,
        )
        self.assertEqual(
            pikaur("-S abduco-git").returncode, 131,
        )
        self.assertInstalled("abduco")
        self.assertNotInstalled("abduco-git")

    def test_cache_clean(self):
        # pylint:disable=import-outside-toplevel
        from pikaur.config import BuildCachePath, PackageCachePath

        pikaur("-S python-pygobject-stubs --rebuild --keepbuild")
        self.assertGreaterEqual(
            len(os.listdir(BuildCachePath()())), 1,
        )
        self.assertGreaterEqual(
            len(os.listdir(PackageCachePath()())), 1,
        )

        pikaur("-Sc --noconfirm")
        self.assertFalse(
            BuildCachePath()().exists(),
        )
        self.assertGreaterEqual(
            len(os.listdir(PackageCachePath()())), 1,
        )

    def test_cache_full_clean(self):
        # pylint:disable=import-outside-toplevel
        from pikaur.config import BuildCachePath, PackageCachePath

        pikaur("-S python-pygobject-stubs --rebuild --keepbuild")
        self.assertGreaterEqual(
            len(os.listdir(BuildCachePath()())), 1,
        )
        self.assertGreaterEqual(
            len(os.listdir(PackageCachePath()())), 1,
        )

        pikaur("-Scc --noconfirm")
        self.assertFalse(
            BuildCachePath()().exists(),
        )
        self.assertFalse(
            PackageCachePath()().exists(),
        )

    def test_print_commands_and_needed(self):
        """Test that `--print--commands` option not fails."""
        self.assertEqual(
            fake_pikaur("-S python-pygobject-stubs nano --print-commands").returncode, 0,
        )

    def test_needed(self):
        """Test that `--needed` option not fails."""
        self.assertEqual(
            pikaur("-S python-pygobject-stubs nano --needed").returncode, 0,
        )
