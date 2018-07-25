""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import os

from pikaur_test.helpers import (
    PikaurDbTestCase,
    pikaur, fake_pikaur, spawn,
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

    def test_pkgbuild(self):
        pkg_name = 'pikaur-git'

        pikaur(f'-R --noconfirm {pkg_name}')
        self.assertNotInstalled(pkg_name)

        pikaur('-P ./PKGBUILD --noconfirm --install')
        self.assertInstalled(pkg_name)

    def test_syu(self):
        """
        test upgrade of repo and AUR packages
        and also -U, -P and -G (during downgrading)
        """
        from pikaur.pacman import PackageDB  # pylint: disable=no-name-in-module

        # just update to make sure everything is on the latest version,
        # except for test subject packages
        pikaur('-Syu --noconfirm')

        # repo package downgrade
        repo_pkg_name = 'nano'
        repo_old_version = '2.9.7-1'
        pikaur(
            '-U --noconfirm '
            'https://archive.archlinux.org/repos/2018/05/17/core/os/x86_64/'
            f'{repo_pkg_name}-{repo_old_version}-x86_64.pkg.tar.xz'
        )
        self.assertEqual(
            PackageDB.get_local_dict()['nano'].version, repo_old_version
        )

        # AUR package downgrade
        aur_pkg_name = 'inxi'
        self.remove_if_installed(aur_pkg_name)
        pikaur(f'-G -d {aur_pkg_name}')
        prev_commit = spawn(f'git -C ./{aur_pkg_name} log --format=%h').stdout_text.splitlines()[1]
        spawn(f'git -C ./{aur_pkg_name} checkout {prev_commit}')
        pikaur(f'-P -i --noconfirm ./{aur_pkg_name}/PKGBUILD')
        self.assertInstalled(aur_pkg_name)
        aur_old_version = PackageDB.get_local_dict()[aur_pkg_name].version

        # test pikaur -Qu
        query_result = pikaur('-Quq --aur').stdout.strip()
        self.assertEqual(
            query_result, aur_pkg_name
        )

        query_result = pikaur('-Quq --repo').stdout.strip()
        self.assertEqual(
            query_result, repo_pkg_name
        )

        query_result = pikaur('-Qu').stdout
        self.assertEqual(
            len(query_result.splitlines()), 2
        )
        self.assertIn(
            aur_pkg_name, query_result
        )
        self.assertIn(
            repo_pkg_name, query_result
        )

        # and finally test the sysupgrade itself
        pikaur('-Syu --noconfirm')
        self.assertNotEqual(
            PackageDB.get_local_dict()[repo_pkg_name].version, repo_old_version
        )
        self.assertNotEqual(
            PackageDB.get_local_dict()[aur_pkg_name].version, aur_old_version
        )

    def test_conflicting_packages(self):
        self.remove_if_installed('pacaur', 'cower-git', 'cower')
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
