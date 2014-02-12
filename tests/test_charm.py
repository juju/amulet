
import os
import sys
import unittest
import yaml

from mock import patch, Mock
from amulet.charm import Builder, run_bzr, get_relation
from amulet.deployer import _default_sentry_template
from charmworldlib.charm import Charm


class BuilderTest(unittest.TestCase):
    def test_does_not_create_yaml_tags(self):
        """Instead of creating yaml safe_load will refuse, fail at write"""
        class customstr(str):
            """A custom Python type yaml would serialise tagged"""
        self.assertIn("!!", yaml.dump(customstr("a")))
        builder = Builder(customstr("acharm"), _default_sentry_template)
        self.assertRaises(yaml.representer.RepresenterError, builder.write_metadata)


class RunBzrTest(unittest.TestCase):
    def test_run_bzr(self):
        out = run_bzr(["rocks"], ".")
        self.assertEquals(out, "It sure does!\n")

    @patch('subprocess.Popen')
    def test_run_bzr_traceback(self, mp):
        mp.side_effect = [Exception("AssertionError: always fails")]
        self.assertRaisesRegexp(Exception, "AssertionError: always fails",
                                run_bzr, ["assert-fail"], ".")

    def test_run_bzr_missing(self):
        env = os.environ.copy()
        env["PATH"] = ""
        self.assertRaisesRegexp(OSError, "bzr not found, do you have Bazaar "
                                "installed?", run_bzr, ["version"], ".",
                                env=env)


RAW_METADATA_YAML = '''
name: charm-name
description: Whatever man
requires:
  relation:
    interface: iname
provides:
  plation:
    interface: aniname
'''


class GetRelationTest(unittest.TestCase):
    @patch('os.path.exists')
    @patch('builtins.open' if sys.version_info > (3,) else '__builtin__.open')
    def test_get_relation_local_charm(self, mock_open, mexists):
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = Mock()
        mock_open.return_value.read.return_value = RAW_METADATA_YAML
        mexists.return_value = True
        self.assertEqual(('provides', 'aniname'),
                         get_relation('/path/to/charm', 'plation'))

    @patch('amulet.charm.Charm')
    def test_get_relation_remote(self, mcharm):
        cdata = {'charm': {'relations': {'requires': {'relname': {'interface':
                                                                  'iname'}}}}}
        mcharm.return_value = Charm.from_charmdata(cdata)
        self.assertEqual(('requires', 'iname'), get_relation('c', 'relname'))

    @patch('os.path.exists')
    @patch('builtins.open' if sys.version_info > (3,) else '__builtin__.open')
    def test_no_relations(self, mock_open, mexists):
        BAD_METADATA_YAML = '''
        name: charm-name
        description: Whatever man
        '''
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = Mock()
        mock_open.return_value.read.return_value = BAD_METADATA_YAML
        mexists.return_value = True
        self.assertRaises(Exception, get_relation, '/path/2/bad/charm', 'noop')

    @patch('os.path.exists')
    @patch('builtins.open' if sys.version_info > (3,) else '__builtin__.open')
    def test_no_match(self, mock_open, mexists):
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = Mock()
        mock_open.return_value.read.return_value = RAW_METADATA_YAML
        mexists.return_value = True
        self.assertEqual((None, None), get_relation('/path/charm', 'noop'))
