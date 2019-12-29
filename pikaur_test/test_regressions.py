""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

# pylint: disable=no-name-in-module

from pikaur_test.helpers import PikaurDbTestCase, fake_pikaur, pikaur


class RegressionTest(PikaurDbTestCase):
    """
    Based on GH-issues
    """

    def test_split_pkgs_aur_deps(self):
        # split aur package with deps from aur (too long to build so use fake makepkg)
        fake_pikaur('-S zfs-dkms')
        self.assertInstalled('zfs-dkms')
        self.assertInstalled('zfs-utils')

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
        # pikaur(f'-S {pkg_name}')
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
        from pikaur.pacman import PackageDB  # pylint:disable=import-outside-toplevel

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

    def test_getpkgbuild_group_package(self):
        result = pikaur('-G gnome', capture_stderr=True)
        self.assertEqual(
            result.returncode, 0
        )
        self.assertIn(
            'cannot be found',
            result.stderr
        )

    def test_splitted_pkg_with_base_deps(self):
        """
        when split packages have base depends section
        those deps should be installed during the build

        see #320
        """
        self.remove_if_installed('python2-twisted', 'python-twisted')
        pikaur('-S python-txtorcon')
        self.assertInstalled('python-txtorcon')
        self.assertInstalled('python-twisted')
        self.assertNotInstalled('python2-twisted')

    def test_sy_only(self):
        """
        When running pikaur -Sy to only update the database indexes,
        Pikaur continues to load the databases off disk if they were updated
        (if you have a slow rotating HDD and many packages,
        it can take some time) then exits with "Nothing to do".
        (pacman just exits).

        see #339
        """
        pikaur('-Syu')

        result_syu = pikaur('-Syu', capture_stdout=True)
        self.assertIn(
            "nothing to do",
            result_syu.stdout.lower()
        )

        result_sy = pikaur('-Sy', capture_stdout=True)
        self.assertNotIn(
            "nothing to do",
            result_sy.stdout.lower()
        )

    def test_aur_rpc_didnt_fully_parsed_srcinfo(self):
        """
        AUR RPC doesn't preserve architecture information:
        https://aur.archlinux.org/rpc/?v=5&type=info&arg[]=mongodb-bin

        the dependencies should be recomputed after cloning AUR repos

        see #427
        """
        self.remove_if_installed('mongodb-bin', 'libcurl-openssl-1.0')
        fake_pikaur('-S mongodb-bin')
        self.assertInstalled('mongodb-bin')
        self.assertNotInstalled('libcurl-openssl-1.0')
