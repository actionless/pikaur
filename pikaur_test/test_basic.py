""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

# pylint: disable=invalid-name

import os
import tempfile

from pikaur_test.helpers import PikaurDbTestCase, pikaur, fake_pikaur, spawn


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
        # pikaur -Qi (pikaur -Qdmq) | grep -i -e Name -e 'Required By' -e '^$'
        # pkg_name = 'python-gaphor'
        # dep_name = 'python-generic'
        pkg_name = 'python-guessit'
        dep_name = 'python-rebulk'
        self.remove_if_installed(pkg_name, dep_name)

        pikaur(f'-S {pkg_name} --mflags=--skippgpcheck')
        self.assertInstalled(pkg_name)
        self.assertInstalled(dep_name)

        # package removal (pacman wrapping test)
        pikaur(f'-Rs {pkg_name} {dep_name} --noconfirm')
        self.assertNotInstalled(pkg_name)
        self.assertNotInstalled(dep_name)

    def test_aur_package_with_alternative_aur_dep(self):
        pkg_name = 'dwm'
        dep_name = 'st'
        dep_alt_name = 'st-git'
        self.remove_if_installed(pkg_name, dep_name, dep_alt_name)

        # aur package with manually chosen aur dep:
        pikaur(f'-S {pkg_name} {dep_alt_name}')
        self.assertInstalled(pkg_name)
        self.assertProvidedBy(dep_name, dep_alt_name)
        self.assertInstalled(dep_alt_name)
        self.assertNotInstalled(dep_name)

    def test_aur_pkg_with_already_installed_alternative_aur_dep(self):
        pkg_name = 'dwm'
        dep_name = 'st'
        dep_alt_name = 'st-git'
        self.remove_if_installed(pkg_name, dep_name, dep_alt_name)

        pikaur(f'-S {dep_alt_name} --mflags=--skippgpcheck')
        self.assertInstalled(dep_alt_name)
        self.assertProvidedBy(dep_name, dep_alt_name)
        self.assertInstalled(dep_alt_name)
        self.assertNotInstalled(dep_name)

        # aur package with aur dep provided by another already installed AUR pkg
        pikaur(f'-S {pkg_name}')
        self.assertInstalled(pkg_name)

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
        pkg_base = 'python-pyalsaaudio'
        pkg_name1 = pkg_base
        pkg_name2 = 'python2-pyalsaaudio'

        self.remove_if_installed(pkg_name1)
        self.remove_if_installed(pkg_name2)

        pikaur(f'-G {pkg_base}')
        pikaur(f'-P ./{pkg_base}/PKGBUILD --noconfirm --install')
        self.assertInstalled(pkg_name1)
        self.assertInstalled(pkg_name2)

    def test_pkgbuild_custom_gpgdir(self):
        pkg_name = "zfs-utils"
        pkg_keys = [
            "4F3BA9AB6D1F8D683DC2DFB56AD860EED4598027",
            "C33DF142657ED1F7C328A2960AB9E991C6AF658B"
        ]
        keyserver = "hkp://keyserver.ubuntu.com:11371"

        with tempfile.TemporaryDirectory() as tmpdirname:
            env = {**os.environ, "GNUPGHOME": tmpdirname}
            commands = [
                "gpg --batch --passphrase  --quick-generate-key 'pikaur@localhost' rsa sign 0",
                *map(lambda key: f'gpg --keyserver {keyserver} --receive-keys {key}', pkg_keys),
                *map(lambda key: f'gpg --quick-lsign-key {key}', pkg_keys),
                f"chmod 755 {tmpdirname}",
                f"chmod 644 {tmpdirname}/pubring.gpg",
                f"chmod 644 {tmpdirname}/trust.gpg"
            ]

            for command in commands:
                spawn(command, env=env)

            pikaur(f'--build-gpgdir {tmpdirname} -S {pkg_name}')
            self.assertInstalled(pkg_name)

        # Cleanup to ensure no impact on other tests
        self.remove_if_installed(pkg_name)

    def test_conflicting_aur_packages(self):
        conflicting_aur_package1 = 'resvg'
        conflicting_aur_package2 = 'resvg-git'
        self.remove_if_installed(
            conflicting_aur_package1,
            conflicting_aur_package2
        )
        self.assertEqual(
            pikaur(
                f'-S {conflicting_aur_package1}'
                f' {conflicting_aur_package2}'
            ).returncode, 131
        )
        self.assertNotInstalled(conflicting_aur_package1)
        self.assertNotInstalled(conflicting_aur_package2)

    def test_conflicting_aur_and_repo_packages(self):
        self.remove_if_installed('pacaur', 'expac-git', 'expac')
        self.assertEqual(
            pikaur('-S expac-git expac').returncode, 131
        )
        self.assertNotInstalled('expac')
        self.assertNotInstalled('expac-git')

    def test_conflicting_aur_and_installed_repo_packages(self):
        self.remove_if_installed('pacaur', 'expac-git', 'expac')
        self.assertEqual(
            pikaur('-S expac').returncode, 0
        )
        self.assertEqual(
            pikaur('-S expac-git').returncode, 131
        )
        self.assertInstalled('expac')
        self.assertNotInstalled('expac-git')

    def test_cache_clean(self):
        # pylint:disable=import-outside-toplevel
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
        # pylint:disable=import-outside-toplevel
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
