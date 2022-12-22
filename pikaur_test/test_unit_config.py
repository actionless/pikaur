"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
# mypy: disable-error-code=no-untyped-def

import configparser
from unittest import mock

from pikaur.config import ConfigSchemaT, PikaurConfigItem
from pikaur_test.helpers import PikaurTestCase


class PikaurConfigItemTestCase(PikaurTestCase):

    example_config_schema: ConfigSchemaT = {
        "test_section": {
            "SomeBoolProperty": {
                "data_type": "bool",
            },
            "SomeIntProperty": {
                "data_type": "int",
            },
            "SomeStrProperty": {
                "data_type": "str",
            },
        },
    }
    config_item_bool: PikaurConfigItem
    config_item_int: PikaurConfigItem
    config_item_str: PikaurConfigItem
    config_patcher: "mock._patch[ConfigSchemaT]"

    @classmethod
    def setUpClass(cls):
        cls.config_patcher = mock.patch(
            "pikaur.config.CONFIG_SCHEMA", new=cls.example_config_schema
        )
        cls.config_patcher.start()
        parser = configparser.RawConfigParser()
        parser.add_section("test_section")
        config_section = configparser.SectionProxy(
            parser=parser,
            name="test_section",
        )
        config_section["SomeBoolProperty"] = "yes"
        config_section["SomeIntProperty"] = "2"
        config_section["SomeStrProperty"] = "pkgname"
        # @TODO: implement allowed value and test for trying to set unallowed value:
        # config_section["SomeStrProperty"] = "foo"
        cls.config_item_bool = PikaurConfigItem(
            section=config_section,
            key="SomeBoolProperty",
        )
        cls.config_item_int = PikaurConfigItem(
            section=config_section,
            key="SomeIntProperty",
        )
        cls.config_item_str = PikaurConfigItem(
            section=config_section,
            key="SomeStrProperty",
        )

    @classmethod
    def tearDownClass(cls):
        cls.config_patcher.start()

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
