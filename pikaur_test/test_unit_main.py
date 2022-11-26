"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
# mypy: disable-error-code=no-untyped-def

import sys

from pikaur.main import OutputEncodingWrapper
from pikaur_test.helpers import PikaurTestCase


class MainHelperFuncsTest(PikaurTestCase):

    def test_output_encoding_wrapper(self):
        real_stdout = sys.stdout
        real_stderr = sys.stderr
        print(1)
        with OutputEncodingWrapper():
            print('test')

            # fails if testrunner (like nosetests) capturing output:
            # self.assertNotEqual(real_stdout, sys.stdout)

            # self.assertNotEqual(real_stderr, sys.stderr)
            print(2)
        print(3)
        self.assertEqual(real_stdout, sys.stdout)
        self.assertEqual(real_stderr, sys.stderr)

    def test_output_encoding_wrapper_2(self):
        real_stdout = sys.stdout
        real_stderr = sys.stderr
        print(1)
        with self.assertRaises(SystemExit):
            with OutputEncodingWrapper():
                print('test')

                # fails if testrunner (like nosetests) capturing output:
                # self.assertNotEqual(real_stdout, sys.stdout)

                # self.assertNotEqual(real_stderr, sys.stderr)
                raise Exception('test')
        print(3)
        self.assertEqual(real_stdout, sys.stdout)
        self.assertEqual(real_stderr, sys.stderr)
