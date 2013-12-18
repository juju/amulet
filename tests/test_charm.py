
import unittest
import yaml

from amulet.charm import Builder
from amulet.deployer import _default_sentry_template


class BuilderTest(unittest.TestCase):

    def test_does_not_create_yaml_tags(self):
        """Instead of creating yaml safe_load will refuse, fail at write"""
        class customstr(str):
            """A custom Python type yaml would serialise tagged"""
        self.assertIn("!!", yaml.dump(customstr("a")))
        builder = Builder(customstr("acharm"), _default_sentry_template)
        self.assertRaises(yaml.YAMLError, builder.write_metadata)
