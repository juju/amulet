
import os
import unittest
import yaml

from amulet.charm import Builder, run_bzr
from amulet.deployer import _default_sentry_template


class BuilderTest(unittest.TestCase):

    def test_does_not_create_yaml_tags(self):
        """Instead of creating yaml safe_load will refuse, fail at write"""
        class customstr(str):
            """A custom Python type yaml would serialise tagged"""
        self.assertIn("!!", yaml.dump(customstr("a")))
        builder = Builder(customstr("acharm"), _default_sentry_template)
        self.assertRaises(yaml.YAMLError, builder.write_metadata)


class RunBzrTest(unittest.TestCase):

    def test_run_bzr(self):
        out = run_bzr(["rocks"], ".")
        self.assertEquals(out, "It sure does!\n")

    def test_run_bzr_traceback(self):
        self.assertRaisesRegexp(Exception, "AssertionError: always fails",
            run_bzr, ["assert-fail"], ".")

    def test_run_bzr_missing(self):
        env = os.environ.copy()
        env["PATH"] = ""
        self.assertRaisesRegexp(Exception, "bzr not found",
            run_bzr, ["version"], ".", env=env)
