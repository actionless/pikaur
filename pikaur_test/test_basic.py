""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

# pylint: disable=no-name-in-module

import os

from pikaur_test.helpers import PikaurDbTestCase, pikaur, fake_pikaur


class InstallTest(PikaurDbTestCase):
    """
    basic installation cases
    """

    def test_aur_package_with_repo_deps(self):
        # aur package with repo deps
        pikaur('-S inxi')
        self.assertInstalled('inxi')

    def test_repo_package_wo_deps(self):
        # repo package w/o deps
        pikaur('-S nano')
        self.assertInstalled('nano')

    def test_repo_package_with_deps(self):
        # repo package with deps
        pikaur('-S flac')
        self.assertInstalled('flac')

    def test_aur_package_with_aur_dep(self):
        # aur package with aur dep and custom makepkg flags
        pikaur('-S pacaur-no-ud --mflags=--skippgpcheck')
        self.assertInstalled('pacaur-no-ud')
        self.assertInstalled('cower')

        # package removal (pacman wrapping test)
        pikaur('-Rs pacaur-no-ud cower --noconfirm')
        self.assertNotInstalled('pacaur-no-ud')
        self.assertNotInstalled('cower')

        pikaur('-S cower-git --mflags=--skippgpcheck')
        self.assertInstalled('cower-git')

        # aur package with aur dep provided by another already installed AUR pkg
        pikaur('-S pacaur-no-ud')
        self.assertInstalled('pacaur-no-ud')
        self.assertProvidedBy('cower', 'cower-git')

        self.remove_packages('pacaur-no-ud', 'cower-git')

        # aur package with manually chosen aur dep:
        pikaur('-S pacaur-no-ud cower-git')
        self.assertInstalled('pacaur-no-ud')
        self.assertProvidedBy('cower', 'cower-git')

    def test_pkgbuild(self):
        pkg_name = 'pikaur-git'

        pikaur(f'-R --noconfirm {pkg_name}')
        self.assertNotInstalled(pkg_name)

        pikaur('-P ./PKGBUILD --noconfirm --install')
        self.assertInstalled(pkg_name)

        pikaur(f'-R --noconfirm {pkg_name}')
        self.assertNotInstalled(pkg_name)

        pikaur('-P --noconfirm --install')
        self.assertInstalled(pkg_name)

    def test_pkgbuild_split_packages(self):
        pkg_base = 'python-flake8-polyfill'
        pkg_name1 = pkg_base
        pkg_name2 = 'python2-flake8-polyfill'

        self.remove_if_installed(pkg_name1)
        self.remove_if_installed(pkg_name2)

        pikaur(f'-G {pkg_base}')
        pikaur(f'-P ./{pkg_base}/PKGBUILD --noconfirm --install')
        self.assertInstalled(pkg_name1)
        self.assertInstalled(pkg_name2)

    def test_conflicting_packages(self):
        self.remove_if_installed('pacaur-no-ud', 'cower-git', 'cower')
        self.assertEqual(
            pikaur('-S cower-git cower').returncode, 131
        )
        self.assertNotInstalled('cower')
        self.assertNotInstalled('cower-git')

    def test_cache_clean(self):
        from pikaur.config import BUILD_CACHE_PATH, PACKAGE_CACHE_PATH

        pikaur('-S inxi --rebuild --keepbuild')
        self.assertGreaterEqual(
            len(os.listdir(BUILD_CACHE_PATH)), 1
        )
        self.assertGreaterEqual(
            len(os.listdir(PACKAGE_CACHE_PATH)), 1
        )

        pikaur('-Sc --noconfirm')
        self.assertFalse(
            os.path.exists(BUILD_CACHE_PATH)
        )
        self.assertGreaterEqual(
            len(os.listdir(PACKAGE_CACHE_PATH)), 1
        )

    def test_cache_full_clean(self):
        from pikaur.config import BUILD_CACHE_PATH, PACKAGE_CACHE_PATH

        pikaur('-S inxi --rebuild --keepbuild')
        self.assertGreaterEqual(
            len(os.listdir(BUILD_CACHE_PATH)), 1
        )
        self.assertGreaterEqual(
            len(os.listdir(PACKAGE_CACHE_PATH)), 1
        )

        pikaur('-Scc --noconfirm')
        self.assertFalse(
            os.path.exists(BUILD_CACHE_PATH)
        )
        self.assertFalse(
            os.path.exists(PACKAGE_CACHE_PATH)
        )

    def test_print_commands_and_needed(self):
        """
        test what --print--commands option not fails
        """
        self.assertEqual(
            fake_pikaur('-S inxi nano --print-commands').returncode, 0
        )

    def test_needed(self):
        """
        test what --needed option not fails
        """
        self.assertEqual(
            pikaur('-S inxi nano --needed').returncode, 0
        )
