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
        # with doubled aur dep
        # python-xdis>=5.0.4, python-xdis<5.1.0
        pkg_name = 'python-uncompyle6'

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
        output = ""
        while "nothing to do" not in output:
            result_syu = pikaur('-Syu --ignore pikaur-git', capture_stdout=True)
            output = result_syu.stdout.lower()

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
        pkg_name = 'mongodb-bin'
        wrong_arch_dep_name = 'libcurl-openssl-1.0'
        self.remove_if_installed(pkg_name, wrong_arch_dep_name)
        fake_pikaur(f'-S {pkg_name}')
        self.assertInstalled(pkg_name)
        self.assertNotInstalled(wrong_arch_dep_name)

    def test_aur_rpc_didnt_fully_parsed_srcinfo_2(self):
        """
        Similar situation as with mongodb-bin above but the opposite
        """
        pkg_name = 'guitar-pro'
        correct_arch_dep_name = 'lib32-portaudio'
        self.remove_if_installed(pkg_name, correct_arch_dep_name)
        fake_pikaur(f'-S {pkg_name}')
        self.assertInstalled(pkg_name)
        self.assertInstalled(correct_arch_dep_name)

    def test_version_matcher_on_pkg_install(self):
        """
        https://github.com/actionless/pikaur/issues/474
        """
        aur_pkg_name = 'inxi'
        self.remove_if_installed(aur_pkg_name)
        fake_pikaur(f'-S {aur_pkg_name}>=99.9.9.9')
        self.assertNotInstalled(aur_pkg_name)
        fake_pikaur(f'-S {aur_pkg_name}>=1.0')
        self.assertInstalled(aur_pkg_name)
