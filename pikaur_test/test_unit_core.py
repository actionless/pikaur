""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """
# pylint: disable=invalid-name,disallowed-name

from typing import Any

from pikaur_test.helpers import PikaurTestCase
from pikaur.core import ComparableType, DataType, InstallInfo, PackageSource
from pikaur.pacman import PackageDB
from pikaur.aur import find_aur_packages


class ClassA(ComparableType):
    __ignore_in_eq__ = ('bar', )
    foo: Any
    bar: Any


class ClassB(ComparableType):
    pass


class ComparableTypeTest(PikaurTestCase):

    def test_eq(self):
        a1 = ClassA()
        a1.foo = 1
        a2 = ClassA()
        a2.foo = 1
        self.assertEqual(a1, a2)

    def test_neq(self):
        a1 = ClassA()
        a1.foo = 1
        a2 = ClassA()
        a2.foo = 2
        self.assertNotEqual(a1, a2)

    def test_ignore_1(self):
        a1 = ClassA()
        a1.foo = 1
        a2 = ClassA()
        a2.foo = 1
        self.assertEqual(a1, a2)
        a1.bar = 2
        a2.bar = 3
        self.assertEqual(a1, a2)

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


class DataClass1(DataType):
    foo: int
    bar: str


class DataTypeTest(PikaurTestCase):

    def test_attr(self):
        a1 = DataClass1(foo=1, bar='a')
        self.assertEqual(a1.foo, 1)
        self.assertEqual(a1.bar, 'a')

    def test_init_err(self):
        with self.assertRaises(TypeError):
            DataClass1(foo=1)

    def test_set_unknown(self):
        a1 = DataClass1(foo=1, bar='a')
        with self.assertRaises(TypeError):
            a1.baz = 'baz'  # pylint: disable=attribute-defined-outside-init



class InstallInfoTest(PikaurTestCase):

    @classmethod
    def setUpClass(cls):
        repo_pkg = PackageDB.get_repo_list()[0]
        cls.repo_install_info = InstallInfo(
            name=repo_pkg.name,
            current_version=repo_pkg.version,
            new_version=420,
            package=repo_pkg
        )
        aur_pkg = find_aur_packages(('pikaur', ))[0][0]
        cls.aur_install_info = InstallInfo(
            name=aur_pkg.name,
            current_version=aur_pkg.version,
            new_version=420,
            package=aur_pkg
        )

    def test_basic(self):
        self.assertTrue(self.repo_install_info)

    def test_package_source(self):
        self.assertEqual(self.repo_install_info.package_source, PackageSource.REPO)
        self.assertEqual(self.aur_install_info.package_source, PackageSource.AUR)
