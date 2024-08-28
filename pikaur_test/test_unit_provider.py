"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
# mypy: disable-error-code=no-untyped-def

from unittest.mock import patch

from pikaur.pikatypes import AURPackageInfo
from pikaur.print_department import print_package_search_results
from pikaur.provider import Provider
from pikaur_test.helpers import InterceptSysOutput, PikaurTestCase


class ProviderTest(PikaurTestCase):

    def test_choose_aur_sorted(self):
        options = [
            AURPackageInfo(packagebase=name, name=name, version="0", provides=["foo"])
            for name in ["foo3", "foo2", "foo1"]
        ]
        sorted_options = print_package_search_results(
            aur_packages=options,
            repo_packages=[],
            local_pkgs_versions={},
        )
        # check returned list ordered
        self.assertEqual(options[0], sorted_options[2])

        with (
            InterceptSysOutput() as intercepted,
            patch("pikaur.prompt.get_input", return_value="3") as get_input,
        ):
            chosen = Provider.choose(dependency="foo", options=options)

            # check input taken
            get_input.assert_called_once()

            # check final outcome
            self.assertEqual(chosen, options[0])

        # check prompt message ordered
        for idx in [1, 2, 3]:
            self.assertIn(f"{idx}) aur foo{idx}", intercepted.stdout_text)
