""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

# pylint: disable=no-name-in-module

from pikaur_test.helpers import (
    PikaurDbTestCase,
    pikaur, spawn,
)

from pikaur.pacman import PackageDB  # pylint: disable=no-name-in-module


class SysupgradeTest(PikaurDbTestCase):
    """
    sysupgrade-related test cases
    """

    repo_pkg_name = 'words'
    repo_old_version: str

    repo2_pkg_name = 'tree'
    repo2_old_version: str

    aur_pkg_name = 'etc-update'
    aur_old_version: str

    aur2_pkg_name = 'inxi'
    aur2_old_version: str

    dev_pkg_name = 'xst-git'
    dev_pkg_url = 'git://github.com/gnotclub/xst.git'
    dev_old_version: str

    def setUp(self):
        # just update to make sure everything is on the latest version,
        # except for test subject packages
        pikaur('-Syu --noconfirm')

    def downgrade_repo1_pkg(self):
        self.repo_old_version = self.downgrade_repo_pkg(self.repo_pkg_name)

    def downgrade_repo2_pkg(self):
        self.repo2_old_version = self.downgrade_repo_pkg(self.repo2_pkg_name)

    def downgrade_aur1_pkg(self):
        self.aur_old_version = self.downgrade_aur_pkg(self.aur_pkg_name)

    def downgrade_aur2_pkg(self):
        self.aur2_old_version = self.downgrade_aur_pkg(self.aur2_pkg_name, count=1)

    def downgrade_dev_pkg(self):
        # test -P <custom_name> and -G -d during downgrading
        self.remove_if_installed(self.dev_pkg_name)
        spawn(f'rm -fr ./{self.dev_pkg_name}')
        pikaur(f'-G -d {self.dev_pkg_name}')
        dev_pkg_url = self.dev_pkg_url.replace('/', r'\/')
        spawn([
            "bash",
            "-c",
            f"cd ./{self.dev_pkg_name}/ && "
            "sed -e 's/"
            "^source=.*"
            "/"
            f'source=("git+{dev_pkg_url}#branch=master~1")'
            "/' PKGBUILD > PKGBUILD_prev"
        ])
        pikaur(f'-P -i --noconfirm ./{self.dev_pkg_name}/PKGBUILD_prev')
        self.assertInstalled(self.dev_pkg_name)
        self.dev_old_version = PackageDB.get_local_dict()[self.dev_pkg_name].version

    def test_devel_upgrade(self):
        """
        test upgrade of AUR dev package
        """

        self.downgrade_dev_pkg()

        query_result = pikaur('-Qu').stdout
        self.assertEqual(
            len(query_result.splitlines()), 0
        )

        # and finally test the sysupgrade itself
        pikaur('-Su --noconfirm --devel --ignore pikaur-git')
        # pikaur(f'-S {self.dev_pkg_name} --noconfirm --devel')
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.dev_pkg_name].version,
            self.dev_old_version
        )

    def test_syu(self):
        """
        test upgrade of repo and AUR packages
        """

        self.downgrade_repo1_pkg()
        self.downgrade_aur1_pkg()

        query_result = pikaur('-Quq --aur').stdout
        self.assertEqual(
            query_result.splitlines(), [self.aur_pkg_name]
        )

        query_result = pikaur('-Quq --repo').stdout
        self.assertEqual(
            query_result.splitlines(), [self.repo_pkg_name]
        )

        query_result = pikaur('-Qu').stdout
        self.assertEqual(
            len(query_result.splitlines()), 2
        )
        self.assertIn(
            self.aur_pkg_name, query_result
        )
        self.assertIn(
            self.repo_pkg_name, query_result
        )

        # and finally test the sysupgrade itself
        pikaur('-Su --noconfirm')
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.repo_pkg_name].version,
            self.repo_old_version
        )
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.aur_pkg_name].version,
            self.aur_old_version
        )

    def test_syu_ignore(self):
        """
        test --ignore flag with sysupgrade
        """

        self.downgrade_repo1_pkg()
        self.downgrade_repo2_pkg()
        self.downgrade_aur1_pkg()
        self.downgrade_aur2_pkg()

        # ignore all upgradeable packages
        pikaur(
            '-Su --noconfirm '
            f'--ignore {self.repo_pkg_name} '
            f'--ignore {self.aur_pkg_name} '
            f'--ignore {self.repo2_pkg_name} '
            f'--ignore {self.aur2_pkg_name}'
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.repo_pkg_name].version,
            self.repo_old_version
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.aur_pkg_name].version,
            self.aur_old_version
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.repo2_pkg_name].version,
            self.repo2_old_version
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.aur2_pkg_name].version,
            self.aur2_old_version
        )

        # ignore one of repo pkgs and one of AUR pkgs
        pikaur(
            '-Su --noconfirm '
            f'--ignore {self.repo_pkg_name} '
            f'--ignore {self.aur_pkg_name}'
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.repo_pkg_name].version,
            self.repo_old_version
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.aur_pkg_name].version,
            self.aur_old_version
        )
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.repo2_pkg_name].version,
            self.repo2_old_version
        )
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.aur2_pkg_name].version,
            self.aur2_old_version
        )

        # ignore the only remaining AUR package
        pikaur('-Su --noconfirm '
               f'--ignore {self.aur_pkg_name}')
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.repo_pkg_name].version,
            self.repo_old_version
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.aur_pkg_name].version,
            self.aur_old_version
        )

        self.downgrade_repo1_pkg()

        # ignore the only one remaining repo package
        pikaur('-Su --noconfirm '
               f'--ignore {self.repo_pkg_name}')
        self.assertEqual(
            PackageDB.get_local_dict()[self.repo_pkg_name].version,
            self.repo_old_version
        )
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.aur_pkg_name].version,
            self.aur_old_version
        )

    def test_syu_aur_repo_flags(self):
        """
        test --aur and --repo flags with sysupgrade
        """

        self.downgrade_repo1_pkg()
        self.downgrade_aur1_pkg()

        pikaur('-Su --noconfirm --repo')
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.repo_pkg_name].version,
            self.repo_old_version
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.aur_pkg_name].version,
            self.aur_old_version
        )

        self.downgrade_repo1_pkg()

        pikaur('-Su --noconfirm --aur')
        self.assertEqual(
            PackageDB.get_local_dict()[self.repo_pkg_name].version,
            self.repo_old_version
        )
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.aur_pkg_name].version,
            self.aur_old_version
        )
