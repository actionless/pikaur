"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
# mypy: disable-error-code=no-untyped-def
# pylint: disable=invalid-name,disallowed-name

from typing import Any

from pikaur.aur import find_aur_packages
from pikaur.core import ComparableType, DataType, InstallInfo, PackageSource, get_chunks
from pikaur.pacman import PackageDB
from pikaur_test.helpers import PikaurTestCase


class ComparableTypeTest(PikaurTestCase):

    ClassA: type
    ClassB: type

    @classmethod
    def setUpClass(cls):

        class ClassA(ComparableType):
            __ignore_in_eq__ = ('bar', )
            foo: Any
            bar: Any

        class ClassB(ComparableType):
            pass

        cls.ClassA = ClassA
        cls.ClassB = ClassB

    def test_eq(self):
        a1 = self.ClassA()
        a1.foo = 1
        a2 = self.ClassA()
        a2.foo = 1
        self.assertEqual(a1, a2)

    def test_neq(self):
        a1 = self.ClassA()
        a1.foo = 1
        a2 = self.ClassA()
        a2.foo = 2
        self.assertNotEqual(a1, a2)

    def test_ignore_1(self):
        a1 = self.ClassA()
        a1.foo = 1
        a2 = self.ClassA()
        a2.foo = 1
        self.assertEqual(a1, a2)
        a1.bar = 2
        a2.bar = 3
        self.assertEqual(a1, a2)

    def test_different_types(self):
        a1 = self.ClassA()
        b1 = self.ClassB()
        self.assertNotEqual(a1, b1)

    def test_recursion_1(self):
        a1 = self.ClassA()
        a1.foo = a1
        a2 = self.ClassA()
        a2.foo = a2
        self.assertNotEqual(a1, a2)

    def test_recursion_2(self):
        a1 = self.ClassA()
        a1.foo = a1
        self.assertEqual(a1, a1)

    def test_recursion_3(self):
        a1 = self.ClassA()
        a1.foo = a1
        a2 = self.ClassA()
        a2.foo = a1
        self.assertEqual(a1, a2)


class DataTypeTest(PikaurTestCase):

    DataClass1: type

    @classmethod
    def setUpClass(cls):

        class DataClass1(DataType):
            foo: int
            bar: str

        cls.DataClass1 = DataClass1

    def test_attr(self):
        a1 = self.DataClass1(foo=1, bar='a')
        self.assertEqual(a1.foo, 1)
        self.assertEqual(a1.bar, 'a')

    def test_init_err(self):
        with self.assertRaises(TypeError):
            self.DataClass1(foo=1)

    def test_set_unknown(self):
        a1 = self.DataClass1(foo=1, bar='a')
        with self.assertRaises(TypeError):
            a1.baz = 'baz'  # pylint: disable=attribute-defined-outside-init


class InstallInfoTest(PikaurTestCase):

    repo_install_info: InstallInfo
    aur_install_info: InstallInfo

    @classmethod
    def setUpClass(cls):
        repo_pkg = PackageDB.get_repo_list()[0]
        cls.repo_install_info = InstallInfo(
            name=repo_pkg.name,
            current_version=repo_pkg.version,
            new_version=420,
            package=repo_pkg
        )
        aur_pkg = find_aur_packages(['pikaur', ])[0][0]
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


class MiscCoreFuncsTest(PikaurTestCase):

    def test_get_chunks(self):
        chungus = [1, 2, 3, 4, 5]
        for chunk_size, result in (
            (1, [[1], [2], [3], [4], [5]]),
            (2, [[1, 2], [3, 4], [5]]),
            (3, [[1, 2, 3], [4, 5]]),
            (5, [[1, 2, 3, 4, 5]]),
        ):
            self.assertEqual(
                list(get_chunks(chungus, chunk_size=chunk_size)),
                result
            )
        for chunk_size in (0, -1, ):
            with self.assertRaises(ValueError):
                list(get_chunks(chungus, chunk_size))
