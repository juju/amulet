
import os
import sys
import tempfile
import unittest
import yaml
import shutil

from mock import patch, Mock, call
from amulet.deployer import _default_sentry_template

from amulet.charm import (
    Builder,
    run_bzr,
    get_relation,
    Charm,
    LocalCharm,
    LaunchpadCharm,
    setup_bzr,
    get_charm,
)


class BuilderTest(unittest.TestCase):
    def test_does_not_create_yaml_tags(self):
        """Instead of creating yaml safe_load will refuse, fail at write"""
        class customstr(str):
            """A custom Python type yaml would serialise tagged"""
        self.assertIn("!!", yaml.dump(customstr("a")))
        builder = Builder(customstr("acharm"), _default_sentry_template)
        self.assertRaises(yaml.representer.RepresenterError,
                          builder.write_metadata)
        shutil.rmtree(builder.charm)


class RunBzrTest(unittest.TestCase):
    def test_run_bzr(self):
        out = run_bzr(["rocks"], ".")
        self.assertEquals(out, "It sure does!\n")

    @patch('subprocess.Popen')
    def test_run_bzr_traceback(self, mp):
        mp.side_effect = [Exception("AssertionError: always fails")]
        self.assertRaisesRegexp(Exception, "AssertionError: always fails",
                                run_bzr, ["assert-fail"], ".")

    @patch('subprocess.Popen')
    def test_run_bzr_oserror(self, mp):
        mp.side_effect = [OSError(1, "Command failed")]
        self.assertRaisesRegexp(OSError, "Command failed",
                                run_bzr, ["assert-fail"], ".")

    def test_run_bzr_missing(self):
        env = os.environ.copy()
        env["PATH"] = ""
        self.assertRaisesRegexp(OSError, "bzr not found, do you have Bazaar "
                                "installed?", run_bzr, ["version"], ".",
                                env=env)


class SetupBzrTest(unittest.TestCase):
    @patch('amulet.helpers.run_bzr')
    def test_setup_bzr(self, mp):
        mp.side_effect = [IOError("bzr command failed!"), None, None]
        setup_bzr('/path')
        self.assertEqual(mp.call_args_list,
                         [call(['whoami'], '/path'),
                          call(['whoami', 'amulet@dummy-user.tld'], '/path'),
                          call(['init'], '/path')])


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


class LocalCharmTest(unittest.TestCase):
    @patch('os.path.exists')
    @patch.object(LocalCharm, '_load')
    def test_parse(self, mlc_l, me):
        me.return_value = True
        mlc_l.return_value = {'name': 'test',
                              'author': 'ohkay',
                              'provides': {'rel': {'interface': 'test'}}}
        c = LocalCharm('/path/to/test')
        self.assertEqual('test', c.name)
        mlc_l.assert_called_with('/path/to/test/metadata.yaml')

    def test_make_temp(self):
        charm_dir = tempfile.mkdtemp()
        metadata = {}
        with open(os.path.join(charm_dir, 'metadata.yaml'), 'w') as f:
            f.write(yaml.dump(metadata))

        c = LocalCharm(charm_dir)
        code_source = c.code_source['location']
        self.assertTrue(code_source != charm_dir)
        self.assertTrue(code_source.startswith('/tmp/charm'))
        self.assertTrue(os.path.exists(os.path.join(code_source, '.bzr')))
        self.assertTrue(os.path.exists(os.path.join(
            code_source, 'metadata.yaml')))

        del c
        self.assertFalse(os.path.exists(os.path.join(code_source, '../')))


class LaunchpadCharmTest(unittest.TestCase):
    pass


class GetCharmTest(unittest.TestCase):
    def test_local(self):
        with patch('amulet.charm.LocalCharm') as LocalCharm:
            with patch.dict('amulet.charm.os.environ', {}):
                get_charm('local:precise/mycharm')
                LocalCharm.assert_called_once_with('precise/mycharm')
                LocalCharm.reset_mock()

            with patch.dict('amulet.charm.os.environ', {
                    'JUJU_REPOSITORY': '~/charms'}):
                get_charm('local:precise/mycharm')
                LocalCharm.assert_called_once_with('~/charms/precise/mycharm')
