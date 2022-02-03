""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """
# pylint: disable=invalid-name,disallowed-name

from pikaur_test.helpers import PikaurTestCase
from pikaur.core import ComparableType


class ClassA(ComparableType):
    __ignore_in_eq__ = ('baz', )
    foo: ComparableType


class ClassB(ComparableType):
    pass


class ComparableTypeTest(PikaurTestCase):

    def test_different_types(self):
        a1 = ClassA()
        b1 = ClassB()
        with self.assertRaises(TypeError):
            _ = a1 == b1

    def test_recursion_1(self):
        a1 = ClassA()
        a1.foo = a1
        a2 = ClassA()
        a2.foo = a2
        self.assertNotEqual(a1, a2)

    def test_recursion_2(self):
        a1 = ClassA()
        a1.foo = a1
        self.assertEqual(a1, a1)

    def test_recursion_3(self):
        a1 = ClassA()
        a1.foo = a1
        a2 = ClassA()
        a2.foo = a1
        self.assertEqual(a1, a2)
