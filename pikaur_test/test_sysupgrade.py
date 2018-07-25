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

    repo_pkg_name = 'tree'
    repo_old_version: str

    aur_pkg_name = 'inxi'
    aur_old_version: str

    def setUp(self):
        # just update to make sure everything is on the latest version,
        # except for test subject packages
        pikaur('-Syu --noconfirm')

    def downgrade_repo_pkg(self):
        self.remove_if_installed(self.repo_pkg_name)
        pikaur(f'-G -d {self.repo_pkg_name}')
        some_older_commit = spawn(
            f'git -C ./{self.repo_pkg_name} log --format=%h'
        ).stdout_text.splitlines()[10]
        spawn(f'git -C ./{self.repo_pkg_name} checkout {some_older_commit}')
        pikaur(f'-P -i --noconfirm --mflags=--skippgpcheck '
               f'./{self.repo_pkg_name}/trunk/PKGBUILD')
        self.assertInstalled(self.repo_pkg_name)
        self.repo_old_version = PackageDB.get_local_dict()[self.repo_pkg_name].version

    def downgrade_aur_pkg(self):
        self.remove_if_installed(self.aur_pkg_name)
        pikaur(f'-G -d {self.aur_pkg_name}')
        prev_commit = spawn(
            f'git -C ./{self.aur_pkg_name} log --format=%h'
        ).stdout_text.splitlines()[1]
        spawn(f'git -C ./{self.aur_pkg_name} checkout {prev_commit}')
        pikaur(f'-P -i --noconfirm ./{self.aur_pkg_name}/PKGBUILD')
        self.assertInstalled(self.aur_pkg_name)
        self.aur_old_version = PackageDB.get_local_dict()[self.aur_pkg_name].version

    def test_syu(self):
        """
        test upgrade of repo and AUR packages
        and also -U, -P and -G (during downgrading)
        """

        self.downgrade_repo_pkg()
        self.downgrade_aur_pkg()

        query_result = pikaur('-Quq --aur').stdout.strip()
        self.assertEqual(
            query_result, self.aur_pkg_name
        )

        query_result = pikaur('-Quq --repo').stdout.strip()
        self.assertEqual(
            query_result, self.repo_pkg_name
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
        pikaur('-Syu --noconfirm')
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.repo_pkg_name].version,
            self.repo_old_version
        )
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.aur_pkg_name].version,
            self.aur_old_version
        )
