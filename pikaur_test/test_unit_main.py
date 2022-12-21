"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
# mypy: disable-error-code=no-untyped-def

import sys
from unittest import mock

from pikaur.main import OutputEncodingWrapper
from pikaur_test.helpers import PikaurTestCase


class MainHelperFuncsTest(PikaurTestCase):

    def test_output_encoding_wrapper(self):
        real_stdout = sys.stdout
        real_stderr = sys.stderr
        with OutputEncodingWrapper():
            # self.assertNotEqual(real_stderr, sys.stderr)

            # fails if testrunner (like nosetests) capturing output:
            # self.assertNotEqual(real_stdout, sys.stdout)

            print("test")
        self.assertEqual(real_stdout, sys.stdout)
        self.assertEqual(real_stderr, sys.stderr)

    def test_output_encoding_wrapper_2(self):
        real_stdout = sys.stdout
        real_stderr = sys.stderr
        with self.assertRaises(SystemExit):
            with OutputEncodingWrapper():
                # self.assertNotEqual(real_stderr, sys.stderr)

                # fails if testrunner (like nosetests) capturing output:
                # self.assertNotEqual(real_stdout, sys.stdout)

                raise Exception("test")  # noqa: EM101
        self.assertEqual(real_stdout, sys.stdout)
        self.assertEqual(real_stderr, sys.stderr)

    def test_output_encoding_wrapper_ascii(self):
        with mock.patch("pikaur.main.DEFAULT_INPUT_ENCODING", new="ascii"):
            real_stdout = sys.stdout
            real_stderr = sys.stderr
            with OutputEncodingWrapper():
                # self.assertNotEqual(real_stderr, sys.stderr)

                # fails if testrunner (like nosetests) capturing output:
                # self.assertNotEqual(real_stdout, sys.stdout)

                print("test")
            self.assertEqual(real_stdout, sys.stdout)
            self.assertEqual(real_stderr, sys.stderr)
