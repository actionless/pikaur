"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
# mypy: disable-error-code=no-untyped-def

from pikaur.exceptions import SysExit
from pikaur.urllib import read_bytes_from_url, get_gzip_from_url

from pikaur_test.helpers import PikaurTestCase


class UrllibTestcase(PikaurTestCase):

    def test_read_bytes(self):
        result = read_bytes_from_url('http://example.com', autoretry=False)
        self.assertIn(b'Example Domain', result)

    def test_read_bytes_error(self):
        with self.assertRaises(SysExit):
            read_bytes_from_url(
                'http://example.com12345678901412380', autoretry=False
            )

    def test_read_bytes_error_optional(self):
        result = read_bytes_from_url(
            'http://example.com12345678901412380', optional=True, autoretry=False
        )
        self.assertEqual(b'', result)

    def test_read_gzip_error(self):
        with self.assertRaises(SysExit):
            get_gzip_from_url(
                'http://example.com', autoretry=False
            )
