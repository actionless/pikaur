""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

from pikaur_test.helpers import PikaurDbTestCase, pikaur, fake_pikaur


class ArchWikiTest(PikaurDbTestCase):
    """
    criterias from arch wiki
    """

    # def test_reliable_parser(self):
        # Arch Wiki: Reliable parser #
        # pikaur('-S aws-cli-git')
        # self.assertInstalled('aws-cli-git')
        # python-yaml dep is not available now

    def test_split_packages_1(self):
        # Split packages 1
        fake_pikaur('-S clion')
        self.assertInstalled('clion')

    def test_split_packages_2(self):
        # Split packages 2: libc++
        fake_pikaur('-S libc++ --mflags=--skippgpcheck,--noextract')
        self.assertInstalled('libc++')

        # Split packages 2: libc++abi (installing already built package)
        pikaur('-S libc++abi')
        self.assertInstalled('libc++abi')

    def test_split_packages_3(self):
        # Split packages 3: 1 split package
        pikaur('-S python-pyalsaaudio')
        self.assertInstalled('python-pyalsaaudio')
        self.assertNotInstalled('python2-pyalsaaudio')

        self.remove_packages('python-pyalsaaudio')

        # Split packages 3: 2 split packages
        pikaur('-S python2-pyalsaaudio python-pyalsaaudio')
        self.assertInstalled('python2-pyalsaaudio')
        self.assertInstalled('python-pyalsaaudio')

    # def test_reliable_solver(self):
        # # Arch Wiki: Reliable solver
        # fake_pikaur('-S ros-lunar-desktop')
        # self.assertInstalled('ros-lunar-desktop')
        # it's slow as hell even with mocked makepkg :(
