""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import os
from unittest import TestCase

from pikaur_test.helpers import (
    pikaur,
    remove_packages,
    assert_installed, assert_not_installed, assert_provided_by
)


WRITE_DB = bool(os.environ.get('WRITE_DB'))


if WRITE_DB:
    class CliTest(TestCase):
        # tests which are modifying local package DB:

        def test_all(self):  # pylint: disable=no-self-use
            # @TODO: split to tests and use self.assert*

            # aur package with repo deps
            pikaur('-S inxi')
            assert_installed('inxi')

            # repo package w/o deps
            pikaur('-S nano')
            assert_installed('nano')

            # repo package with deps
            pikaur('-S flac')
            assert_installed('flac')

            # aur package with aur dep and custom makepkg flags
            pikaur('-S pacaur --mflags=--skippgpcheck')
            assert_installed('pacaur')
            assert_installed('cower')

            # package removal (pacman wrapping test)
            pikaur('-Rs pacaur cower --noconfirm')
            assert_not_installed('pacaur')
            assert_not_installed('cower')

            pikaur('-S cower-git --mflags=--skippgpcheck')
            assert_installed('cower-git')

            # aur package with aur dep provided by another already installed AUR pkg
            pikaur('-S pacaur')
            assert_installed('pacaur')
            assert_provided_by('cower', 'cower-git')

            remove_packages('pacaur', 'cower-git')

            # aur package with manually chosen aur dep:
            pikaur('-S pacaur cower-git')
            assert_installed('pacaur')
            assert_provided_by('cower', 'cower-git')

            # # Arch Wiki: Reliable parser ############################################
            # pikaur('-S aws-cli-git')
            # assert_installed('aws-cli-git')
            # # python-tox dep is not available now

            # # Arch Wiki: Split packages #############################################

            # Split packages 1
            pikaur('-S clion --mflags=--noextract', fake_makepkg=True)
            assert_installed('clion')

            # Split packages 2: libc++
            pikaur('-S libc++ --mflags=--skippgpcheck,--noextract', fake_makepkg=True)
            assert_installed('libc++')

            # Split packages 2: libc++abi (installing already built package)
            pikaur('-S libc++abi')
            assert_installed('libc++abi')

            # Split packages 3: 1 split package
            pikaur('-S python-pyalsaaudio')
            assert_installed('python-pyalsaaudio')
            assert_not_installed('python2-pyalsaaudio')

            remove_packages('python-pyalsaaudio')

            # Split packages 3: 2 split packages
            pikaur('-S python2-pyalsaaudio python-pyalsaaudio')
            assert_installed('python2-pyalsaaudio')
            assert_installed('python-pyalsaaudio')

            # # Arch Wiki: Reliable solver ############################################
            # pikaur('-S ros-lunar-desktop --mflags=--noextract', fake_makepkg=True)
            # assert_installed('ros-lunar-desktop')
            # it's slow as hell even with mocked makepkg :(

            # # Based on GH-issues: ###################################################

            # split aur package with deps from aur (too long to build so use fake makepkg)
            pikaur('-S zfs-dkms --mflags=--noextract', fake_makepkg=True)
            assert_installed('zfs-dkms')
            assert_installed('zfs-utils')
            assert_installed('spl-dkms')
            assert_installed('spl-utils')

            for pkg_name in [
                    # double requirements line
                    # pikaur -Si --aur | grep -e \^name -e \^depends | grep -E "(>.*<|<.*>)" -B 1
                    'xfe',  # with doubled repo dep
                    'python2-uncompyle6',  # with doubled aur dep

                    # depend on versioned requirement provided by few pkgs
                    # 'minecraft-launcher',  # too many deps to download
                    'jetbrains-toolbox',
            ]:
                pikaur(
                    f'-S {pkg_name} --mflags=--noextract',
                    fake_makepkg=True, capture_stdout=True
                )
                assert_installed(pkg_name)
