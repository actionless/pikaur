""" Licensed under GPLv3, see https://www.gnu.org/licenses/ """
# mypy: disable-error-code=no-untyped-def

from pikaur_test.helpers import PikaurTestCase
from pikaur.pikspect import pikspect


class PikspectTest(PikaurTestCase):

    def test_error_argstype(self):
        with self.assertRaises(TypeError):
            pikspect(cmd='echo')  # type: ignore[arg-type]

    def test_basic(self):
        result = pikspect(cmd=['echo', 'test'])
        self.assertEqual(result.output, b'')
        result = pikspect(cmd=['echo', 'test'], capture_output=True)
        self.assertEqual(result.output, b'test\r\n')
        result = pikspect(
            cmd=['bash', '-c', 'echo foo ; sleep 0.1 ; echo bar'],
            capture_output=True
        )
        self.assertEqual(result.output, b'foo\r\nbar\r\n')
