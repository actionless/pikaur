"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
# mypy: disable-error-code=no-untyped-def

from pikaur.args import CachedArgs, parse_args, reconstruct_args
from pikaur_test.helpers import PikaurTestCase


class ReconstructArgsTest(PikaurTestCase):

    def get_reconstructed(self, user_args):
        CachedArgs.args = None
        return reconstruct_args(
            parse_args(args=user_args), ignore_args=["sync"],
        )

    def test_print_format_not_duplicated(self):
        """
        `--print-format` is applied by `get_pacman_command()` already:
        reconstructing it again would duplicate it as an unknown argument.
        """
        reconstructed = self.get_reconstructed(
            ["-S", "--print-format", "%n", "somepkg"],
        )
        self.assertNotIn("--print_format", reconstructed)

    def test_assume_installed_not_duplicated(self):
        """
        https://github.com/actionless/pikaur/issues/633
        `--assume-installed` is applied by `get_pacman_command()` already:
        reconstructing it again produced `--assume_installed`,
        which pacman rejects as an unrecognized option.
        """
        reconstructed = self.get_reconstructed(
            ["-S", "--assume-installed", "java-runtime=17", "somepkg"],
        )
        self.assertNotIn("--assume_installed", reconstructed)
