"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
# mypy: disable-error-code=no-untyped-def

from pikaur_test.helpers import PikaurDbTestCase, fake_pikaur, pikaur


class ArchWikiTest(PikaurDbTestCase):
    """Criteria from arch wiki."""

    def test_reliable_parser(self):
        # Arch Wiki: Reliable parser #
        pikaur("-S aws-cli-git")
        self.assertInstalled("aws-cli-git")

    def test_reliable_solver(self):
        # Arch Wiki: Reliable solver
        self.remove_if_installed("gmock")
        fake_pikaur("-S ros-melodic-desktop")
        self.assertInstalled("ros-melodic-desktop")
        # it's slow as hell even with mocked makepkg :(

    def test_split_packages_1(self):
        # Split packages 1:
        # Multiple packages from the same package base,
        # without rebuilding or reinstalling multiple times, such as clion.
        fake_pikaur("-S clion")
        self.assertInstalled("clion")

    def test_split_packages_2(self):
        # Split packages 2:
        # Split packages which depend on a package from the same package base,
        # such as samsung-unified-driver
        fake_pikaur("-S samsung-unified-driver --mflags=--skippgpcheck")
        self.assertInstalled("samsung-unified-driver")

    def test_split_packages_3(self):
        # Split packages 3:
        # Split packages independently,
        # such as nxproxy and nxagent
        pkg_name_1 = "nxproxy"
        pkg_name_2 = "nxagent"

        fake_pikaur(f"-S {pkg_name_1} --mflags=--skippgpcheck")
        self.assertInstalled(pkg_name_1)
        self.assertNotInstalled(pkg_name_2)

        self.remove_packages(pkg_name_1)
        # Split packages 3: 2 split packages
        fake_pikaur("-S {pkg_name_1} {pkg_name_2} --mflags=--skippgpcheck")
        self.assertInstalled(pkg_name_1)
        self.assertInstalled(pkg_name_2)

    # def test_split_packages_3(self):
    #     # Split packages 3:
    #     # Split packages independently,
    #     # such as nxproxy and nxagent
    #     fake_pikaur("-S lua51-xmlrpc --mflags=--skippgpcheck")
    #     self.assertInstalled("lua51-xmlrpc")
    #     self.assertNotInstalled("lua52-xmlrpc")

    #     self.remove_packages("lua51-xmlrpc")

    #     # Split packages 3: 2 split packages
    #     fake_pikaur("-S lua51-xmlrpc lua52-xmlrpc --mflags=--skippgpcheck")
    #     self.assertInstalled("lua51-xmlrpc")
    #     self.assertInstalled("lua52-xmlrpc")
