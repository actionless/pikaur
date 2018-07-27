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

    repo2_pkg_name = 'expac'
    repo2_old_version: str

    aur2_pkg_name = 'yaourt'
    aur2_old_version: str

    dev_pkg_name = 'termdown-git'
    dev_pkg_url = "https://github.com/trehn/termdown"
    dev_old_version: str

    def setUp(self):
        # just update to make sure everything is on the latest version,
        # except for test subject packages
        pikaur('-Syu --noconfirm')

    def _downgrade_repo_pkg(self, repo_pkg_name: str) -> str:
        self.remove_if_installed(repo_pkg_name)
        spawn(f'rm -fr ./{repo_pkg_name}')
        pikaur(f'-G {repo_pkg_name}')
        some_older_commit = spawn(  # type: ignore
            f'git -C ./{repo_pkg_name} log --format=%h'
        ).stdout_text.splitlines()[10]
        spawn(f'git -C ./{repo_pkg_name} checkout {some_older_commit}')
        pikaur(f'-P -i --noconfirm --mflags=--skippgpcheck '
               f'./{repo_pkg_name}/trunk/PKGBUILD')
        self.assertInstalled(repo_pkg_name)
        return PackageDB.get_local_dict()[repo_pkg_name].version

    def downgrade_repo_pkg(self):
        self.repo_old_version = self._downgrade_repo_pkg(self.repo_pkg_name)

    def downgrade_repo2_pkg(self):
        self.repo2_old_version = self._downgrade_repo_pkg(self.repo2_pkg_name)

    def _downgrade_aur_pkg(self, aur_pkg_name: str) -> str:
        # test -P and -G during downgrading
        self.remove_if_installed(aur_pkg_name)
        spawn(f'rm -fr ./{aur_pkg_name}')
        pikaur(f'-G {aur_pkg_name}')
        prev_commit = spawn(  # type: ignore
            f'git -C ./{aur_pkg_name} log --format=%h'
        ).stdout_text.splitlines()[1]
        spawn(f'git -C ./{aur_pkg_name} checkout {prev_commit}')
        pikaur(f'-P -i --noconfirm ./{aur_pkg_name}/PKGBUILD')
        self.assertInstalled(aur_pkg_name)
        return PackageDB.get_local_dict()[aur_pkg_name].version

    def downgrade_aur_pkg(self):
        self.aur_old_version = self._downgrade_aur_pkg(self.aur_pkg_name)

    def downgrade_aur2_pkg(self):
        self.aur2_old_version = self._downgrade_aur_pkg(self.aur2_pkg_name)

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
            len([l for l in query_result.splitlines() if l]), 0
        )

        # and finally test the sysupgrade itself
        pikaur('-Su --noconfirm --devel')
        # pikaur(f'-S {self.dev_pkg_name} --noconfirm --devel')
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.dev_pkg_name].version,
            self.dev_old_version
        )

    def test_syu(self):
        """
        test upgrade of repo and AUR packages
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

        self.downgrade_repo_pkg()
        self.downgrade_repo2_pkg()
        self.downgrade_aur_pkg()
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

        self.downgrade_repo_pkg()

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

        self.downgrade_repo_pkg()
        self.downgrade_aur_pkg()

        pikaur('-Su --noconfirm --repo')
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.repo_pkg_name].version,
            self.repo_old_version
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.aur_pkg_name].version,
            self.aur_old_version
        )

        self.downgrade_repo_pkg()

        # ignore the only one remaining repo package
        pikaur('-Su --noconfirm --aur')
        self.assertEqual(
            PackageDB.get_local_dict()[self.repo_pkg_name].version,
            self.repo_old_version
        )
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.aur_pkg_name].version,
            self.aur_old_version
        )
