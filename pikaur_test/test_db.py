""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

from pikaur_test.helpers import (
    PikaurDbTestCase,
    pikaur, fake_pikaur,
)


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
        pikaur('-S pacaur --mflags=--skippgpcheck')
        self.assertInstalled('pacaur')
        self.assertInstalled('cower')

        # package removal (pacman wrapping test)
        pikaur('-Rs pacaur cower --noconfirm')
        self.assertNotInstalled('pacaur')
        self.assertNotInstalled('cower')

        pikaur('-S cower-git --mflags=--skippgpcheck')
        self.assertInstalled('cower-git')

        # aur package with aur dep provided by another already installed AUR pkg
        pikaur('-S pacaur')
        self.assertInstalled('pacaur')
        self.assertProvidedBy('cower', 'cower-git')

        self.remove_packages('pacaur', 'cower-git')

        # aur package with manually chosen aur dep:
        pikaur('-S pacaur cower-git')
        self.assertInstalled('pacaur')
        self.assertProvidedBy('cower', 'cower-git')


class ArchWikiTest(PikaurDbTestCase):
    """
    criterias from arch wiki
    """

    # def test_reliable_parser(self):
        # Arch Wiki: Reliable parser #
        # pikaur('-S aws-cli-git')
        # self.assertInstalled('aws-cli-git')
        # python-tox dep is not available now

    def test_split_packages_1(self):
        # Split packages 1
        pikaur('-S clion --mflags=--noextract', fake_makepkg=True)
        self.assertInstalled('clion')

    def test_split_packages_2(self):
        # Split packages 2: libc++
        pikaur('-S libc++ --mflags=--skippgpcheck,--noextract', fake_makepkg=True)
        self.assertInstalled('libc++')

        # Split packages 2: libc++abi (installing already built package)
        pikaur('-S libc++abi')
        self.assertInstalled('libc++abi')

    def test_split_packages_3(self):
        # Split packages 3: 1 split package
        pikaur('-S python-pyalsaaudio')
        self.assertInstalled('python-pyalsaaudio')
        self.assertNotInstalled('python2-pyalsaaudio')

        self.remove_packages('python-pyalsaaudio')

        # Split packages 3: 2 split packages
        pikaur('-S python2-pyalsaaudio python-pyalsaaudio')
        self.assertInstalled('python2-pyalsaaudio')
        self.assertInstalled('python-pyalsaaudio')

    # def test_reliable_solver(self):
        # # Arch Wiki: Reliable solver
        # pikaur('-S ros-lunar-desktop --mflags=--noextract', fake_makepkg=True)
        # self.assertInstalled('ros-lunar-desktop')
        # it's slow as hell even with mocked makepkg :(


class RegressionTest(PikaurDbTestCase):
    """
    Based on GH-issues
    """

    def test_split_pkgs_aur_deps(self):
        # split aur package with deps from aur (too long to build so use fake makepkg)
        fake_pikaur('-S zfs-dkms')
        self.assertInstalled('zfs-dkms')
        self.assertInstalled('zfs-utils')
        self.assertInstalled('spl-dkms')
        self.assertInstalled('spl-utils')

    def test_double_requirements_repo(self):
        # double requirements line
        # pikaur -Si --aur | grep -e \^name -e \^depends | grep -E "(>.*<|<.*>)" -B 1
        # with doubled repo dep
        pkg_name = 'xfe'
        fake_pikaur(f'-S {pkg_name}')
        self.assertInstalled(pkg_name)

    def test_double_requirements_aur(self):
        pkg_name = 'python2-uncompyle6'  # with doubled aur dep
        fake_pikaur(f'-S {pkg_name}')
        self.assertInstalled(pkg_name)

    def test_aur_pkg_with_versioned_virtual_deps(self):
        # depend on versioned requirement provided by few pkgs
        # 'minecraft-launcher',  # too many deps to download
        pkg_name = 'jetbrains-toolbox'
        fake_pikaur(f'-S {pkg_name}')
        self.assertInstalled(pkg_name)
