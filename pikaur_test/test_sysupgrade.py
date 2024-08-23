"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
# mypy: disable-error-code=no-untyped-def

from pikaur.pacman import PackageDB
from pikaur_test.helpers import PikaurDbTestCase, pikaur, spawn


class SysupgradeTest(PikaurDbTestCase):
    """Sysupgrade-related testcases."""

    self_name = "pikaur-git"

    """
    pikaur -Qi (pikaur -Qnq) | grep -e '^Name' -e '^Installed Size' -e '^Depends On' | less -r
    """

    # repo_pkg_name = "ncdu"
    repo_pkg_name = "xmlto"
    repo_old_version: str

    repo2_pkg_name = "xsel"
    repo2_old_version: str

    aur_pkg_name = "fbcat"
    aur_old_version: str

    aur2_pkg_name = "python-pygobject-stubs"
    aur2_old_version: str

    dev_pkg_name = "xst-git"
    dev_pkg_url = "https://github.com/gnotclub/xst.git"
    dev_old_version: str
    dev_downgrade_amount = 1

    def setUp(self):
        # just update to make sure everything is on the latest version,
        # except for test subject packages
        pikaur("-Syu --noconfirm", skippgpcheck=True)

    def downgrade_repo1_pkg(self) -> None:
        self.repo_old_version = self.downgrade_repo_pkg(
            self.repo_pkg_name, fake_makepkg=True,
        )

    def downgrade_repo2_pkg(self) -> None:
        self.repo2_old_version = self.downgrade_repo_pkg(
            self.repo2_pkg_name, fake_makepkg=True, count=2,
        )

    def downgrade_aur1_pkg(self) -> None:
        self.aur_old_version = self.downgrade_aur_pkg(
            self.aur_pkg_name, count=2, fake_makepkg=True, skippgpcheck=True,
        )

    def downgrade_aur2_pkg(self) -> None:
        self.aur2_old_version = self.downgrade_aur_pkg(
            self.aur2_pkg_name, count=3, fake_makepkg=True,
        )

    def downgrade_dev_pkg(self) -> None:
        # test -P <custom_name> and -G -d during downgrading
        self.remove_if_installed(self.dev_pkg_name)
        spawn(f"rm -fr ./{self.dev_pkg_name}")
        pikaur(f"-G -d {self.dev_pkg_name}")
        dev_pkg_url = self.dev_pkg_url.replace("/", r"\/")
        spawn([
            "bash",
            "-c",
            f"cd ./{self.dev_pkg_name}/ && "
            "sed -e 's/"
            "^source=.*"
            "/"
            f'source=("git+{dev_pkg_url}#branch=master~{self.dev_downgrade_amount}")'
            "/' PKGBUILD > PKGBUILD_prev",
        ])
        pikaur(
            f"-P -i --noconfirm ./{self.dev_pkg_name}/PKGBUILD_prev --print-commands",
            fake_makepkg=True, fake_makepkg_noextract=False,
        )
        self.assertInstalled(self.dev_pkg_name)
        self.dev_old_version = PackageDB.get_local_dict()[self.dev_pkg_name].version

    def test_devel_upgrade(self):
        """Test upgrade of AUR dev package."""
        self.downgrade_dev_pkg()

        # and finally test the sysupgrade itself
        pikaur(
            "-Su --noconfirm --devel --ignore pikaur-git",
            fake_makepkg=True, fake_makepkg_noextract=False,
        )
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.dev_pkg_name].version,
            self.dev_old_version,
        )

    @property
    def upgradeable_pkgs_list(self) -> list[str]:
        query_result = pikaur("-Quq").stdout
        upgradeable_pkgs = query_result.splitlines()
        if self.self_name in upgradeable_pkgs:
            upgradeable_pkgs.remove(self.self_name)
        return upgradeable_pkgs

    @property
    def upgradeable_repo_pkgs_list(self) -> list[str]:
        return pikaur("-Quq --repo").stdout.splitlines()

    @property
    def upgradeable_aur_pkgs_list(self) -> list[str]:
        query_result = pikaur("-Quq --aur").stdout
        upgradeable_aur_pkgs = query_result.splitlines()
        if self.self_name in upgradeable_aur_pkgs:
            upgradeable_aur_pkgs.remove(self.self_name)
        return upgradeable_aur_pkgs

    def test_syu(self):
        """Test upgrade of repo and AUR packages."""
        self.downgrade_repo1_pkg()
        self.downgrade_aur1_pkg()

        self.assertEqual(
            self.upgradeable_aur_pkgs_list, [self.aur_pkg_name],
        )
        self.assertEqual(
            self.upgradeable_repo_pkgs_list, [self.repo_pkg_name],
        )
        self.assertEqual(
            sorted(self.upgradeable_pkgs_list),
            sorted([self.repo_pkg_name, self.aur_pkg_name]),
        )

        # and finally test the sysupgrade itself
        pikaur(
            "-Su --noconfirm",
            skippgpcheck=True,
            fake_makepkg=True,
        )
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.repo_pkg_name].version,
            self.repo_old_version,
        )
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.aur_pkg_name].version,
            self.aur_old_version,
        )

    def test_syu_ignore(self):
        """Test `--ignore` flag with `--sysupgrade`."""
        self.downgrade_repo1_pkg()
        self.downgrade_repo2_pkg()
        self.downgrade_aur1_pkg()
        self.downgrade_aur2_pkg()

        # ignore all upgradeable packages
        pikaur(
            "-Su --noconfirm "
            f"--ignore {self.repo_pkg_name} "
            f"--ignore {self.aur_pkg_name} "
            f"--ignore {self.repo2_pkg_name} "
            f"--ignore {self.aur2_pkg_name}",
            fake_makepkg=True,
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.repo_pkg_name].version,
            self.repo_old_version,
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.aur_pkg_name].version,
            self.aur_old_version,
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.repo2_pkg_name].version,
            self.repo2_old_version,
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.aur2_pkg_name].version,
            self.aur2_old_version,
        )

        # ignore one of repo pkgs and one of AUR pkgs
        pikaur(
            "-Su --noconfirm "
            f"--ignore {self.repo_pkg_name} "
            f"--ignore {self.aur_pkg_name}",
            fake_makepkg=True,
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.repo_pkg_name].version,
            self.repo_old_version,
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.aur_pkg_name].version,
            self.aur_old_version,
        )
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.repo2_pkg_name].version,
            self.repo2_old_version,
        )
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.aur2_pkg_name].version,
            self.aur2_old_version,
        )

        # ignore the only remaining AUR package
        pikaur(
            "-Su --noconfirm "
            f"--ignore {self.aur_pkg_name}",
            fake_makepkg=True,
        )
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.repo_pkg_name].version,
            self.repo_old_version,
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.aur_pkg_name].version,
            self.aur_old_version,
        )

        self.downgrade_repo1_pkg()

        # ignore the only one remaining repo package
        pikaur(
            "-Su --noconfirm "
            f"--ignore {self.repo_pkg_name}",
            fake_makepkg=True,
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.repo_pkg_name].version,
            self.repo_old_version,
        )
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.aur_pkg_name].version,
            self.aur_old_version,
        )

    def test_syu_aur_repo_flags(self):
        """Test `--aur` and `--repo` flags with `--sysupgrade`."""
        self.downgrade_repo1_pkg()
        self.downgrade_aur1_pkg()

        pikaur("-Su --noconfirm --repo")
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.repo_pkg_name].version,
            self.repo_old_version,
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.aur_pkg_name].version,
            self.aur_old_version,
        )

        self.downgrade_repo1_pkg()

        pikaur(
            "-Su --noconfirm --aur",
            fake_makepkg=True,
        )
        self.assertEqual(
            PackageDB.get_local_dict()[self.repo_pkg_name].version,
            self.repo_old_version,
        )
        self.assertNotEqual(
            PackageDB.get_local_dict()[self.aur_pkg_name].version,
            self.aur_old_version,
        )
