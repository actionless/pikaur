""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """
from unittest import TestCase

from pikaur_test.helpers import pikaur, pacman


class CliTest(TestCase):

    def test_unknown_argument(self):
        """
        unknown argument passed to pacman
        """
        self.assertEqual(pikaur('-Zyx').returncode, 1)

    def test_search(self):
        self.assertEqual(
            sorted(
                pikaur('-Ssq oomox').stdout.splitlines()
            ),
            ['oomox', 'oomox-git']
        )

    def test_install_not_found(self):
        """
        package can't be found in AUR
        """
        result = pikaur('-S not-existing-aur-package-7h68712683h1628h1')
        self.assertEqual(result.returncode, 6)
        self.assertEqual(
            result.stdout.splitlines()[-1].strip(),
            'not-existing-aur-package-7h68712683h1628h1'
        )

    def test_aur_package_info(self):
        result = pikaur('-Si oomox')
        pkg_name_found = False
        for line in result.stdout.splitlines():
            if 'name' in line and 'oomox' in line:
                pkg_name_found = True
        self.assertTrue(pkg_name_found)

    def test_repo_package_info(self):
        result1 = pikaur('-Si mpv')
        result2 = pacman('-Si mpv')
        self.assertEqual(result1, result2)

    # just run info commands for coverage:

    def test_version(self):
        self.assertEqual(
            pikaur('-V').returncode, 0
        )

    def test_sync_help(self):
        self.assertEqual(
            pikaur('-Sh').returncode, 0
        )

    def test_query_help(self):
        self.assertEqual(
            pikaur('-Qh').returncode, 0
        )
