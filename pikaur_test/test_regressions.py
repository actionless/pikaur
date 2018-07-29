""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

# pylint: disable=no-name-in-module

from pikaur_test.helpers import PikaurDbTestCase, fake_pikaur


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

    def test_explicit_pkgs_not_becoming_deps(self):
        """
        #123 AUR dep which was previously explicitly installed gets
        incorrectly marked as a dependency
        """
        from pikaur.pacman import PackageDB

        aur_pkg_name = 'nqp'
        explicitly_installed_dep_name = 'moarvm'

        self.remove_if_installed(aur_pkg_name, explicitly_installed_dep_name)
        explicitly_installed_dep_old_version = self.downgrade_aur_pkg(
            explicitly_installed_dep_name, fake_makepkg=True
        )
        self.assertInstalled(explicitly_installed_dep_name)
        self.assertEqual(
            PackageDB.get_local_dict()[explicitly_installed_dep_name].reason,
            0
        )

        fake_pikaur(f'-S {aur_pkg_name}')
        self.assertInstalled(aur_pkg_name)
        self.assertInstalled(explicitly_installed_dep_name)
        self.assertNotEqual(
            PackageDB.get_local_dict()[explicitly_installed_dep_name].version,
            explicitly_installed_dep_old_version
        )
        self.assertEqual(
            PackageDB.get_local_dict()[explicitly_installed_dep_name].reason,
            0
        )
