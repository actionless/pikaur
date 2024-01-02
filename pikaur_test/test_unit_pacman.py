"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
# mypy: disable-error-code=no-untyped-def

from pikaur.pacman import PackageDB, RepositoryNotFoundError
from pikaur_test.helpers import PikaurTestCase


class PacmanTestCase(PikaurTestCase):

    def test_error_item_bool_get_str(self):
        with self.assertRaises(RepositoryNotFoundError):
            PackageDB.get_repo_priority(repo_name="some_funny_repo_name")

    def test_find_repo_package_multiple_providers(self):
        found_pkg = PackageDB.find_repo_package("java-runtime")
        self.assertIn("jdk-openjdk", found_pkg.name)
