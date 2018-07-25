""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

# pylint: disable=no-name-in-module

from pikaur_test.helpers import (
    PikaurDbTestCase,
    pikaur, spawn,
)


class SysupgradeTest(PikaurDbTestCase):
    """
    sysupgrade-related test cases
    """

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
        repo_pkg_name = 'tree'
        pikaur(f'-G -d {repo_pkg_name}')
        some_older_commit = spawn(
            f'git -C ./{repo_pkg_name} log --format=%h'
        ).stdout_text.splitlines()[10]
        spawn(f'git -C ./{repo_pkg_name} checkout {some_older_commit}')
        pikaur(f'-P -i --noconfirm --mflags=--skippgpcheck '
               f'./{repo_pkg_name}/trunk/PKGBUILD')
        self.assertInstalled(repo_pkg_name)
        repo_old_version = PackageDB.get_local_dict()[repo_pkg_name].version

        # AUR package downgrade
        aur_pkg_name = 'inxi'
        self.remove_if_installed(aur_pkg_name)
        pikaur(f'-G -d {aur_pkg_name}')
        prev_commit = spawn(
            f'git -C ./{aur_pkg_name} log --format=%h'
        ).stdout_text.splitlines()[1]
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
