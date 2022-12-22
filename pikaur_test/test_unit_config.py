"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
# mypy: disable-error-code=no-untyped-def

import configparser

from pikaur.config import PikaurConfigItem
from pikaur_test.helpers import PikaurTestCase


class PikaurConfigItemTestCase(PikaurTestCase):

    config_section: configparser.SectionProxy
    config_item_bool: PikaurConfigItem
    config_item_int: PikaurConfigItem
    config_item_str: PikaurConfigItem

    @classmethod
    def setUpClass(cls):
        parser = configparser.RawConfigParser()
        parser.add_section("sync")
        cls.config_section = configparser.SectionProxy(
            parser=parser,
            name="sync",
        )
        cls.config_section["AlwaysShowPkgOrigin"] = "yes"
        cls.config_section["DevelPkgsExpiration"] = "2"
        cls.config_section["UpgradeSorting"] = "pkgname"
        # @TODO: implement allowed value and test for trying to set unallowed value:
        # cls.config_section["UpgradeSorting"] = "foo"
        cls.config_item_bool = PikaurConfigItem(
            section=cls.config_section,
            key="AlwaysShowPkgOrigin",
        )
        cls.config_item_int = PikaurConfigItem(
            section=cls.config_section,
            key="DevelPkgsExpiration",
        )
        cls.config_item_str = PikaurConfigItem(
            section=cls.config_section,
            key="UpgradeSorting",
        )

    def test_get_value_bool(self):
        value = self.config_item_bool.value
        typed_value = self.config_item_bool.get_bool()
        self.assertEqual(value, "yes")
        self.assertEqual(typed_value, True)  # noqa: FBT003
        self.assertIsInstance(typed_value, bool)

    def test_get_value_int(self):
        value = self.config_item_int.value
        typed_value = self.config_item_int.get_int()
        self.assertEqual(value, "2")
        self.assertEqual(typed_value, 2)
        self.assertIsInstance(typed_value, int)

    def test_get_value_str(self):
        value = self.config_item_str.value
        typed_value = self.config_item_str.get_str()
        self.assertEqual(value, typed_value)
        self.assertEqual(typed_value, "pkgname")
        self.assertIsInstance(typed_value, str)

    def test_error_item_bool_get_str(self):
        with self.assertRaises(TypeError):
            self.config_item_bool.get_str()

    def test_error_item_bool_get_int(self):
        with self.assertRaises(TypeError):
            self.config_item_bool.get_int()

    def test_error_item_int_get_str(self):
        with self.assertRaises(TypeError):
            self.config_item_int.get_str()

    def test_error_item_int_get_bool(self):
        with self.assertRaises(TypeError):
            self.config_item_int.get_bool()

    def test_error_item_str_get_bool(self):
        with self.assertRaises(TypeError):
            self.config_item_str.get_bool()

    def test_error_item_str_get_int(self):
        with self.assertRaises(TypeError):
            self.config_item_str.get_int()
