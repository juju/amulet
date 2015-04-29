import os
import shutil
import tempfile
import unittest
import yaml

from mock import patch, call

from amulet.charm import CharmCache
from amulet.charm import LocalCharm
from amulet.charm import is_branch
from amulet.charm import run_bzr
from amulet.charm import setup_bzr



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
        # Set one side_effect for each expected call to run_bzr.
        mp.side_effect = [IOError("bzr command failed!"), None, None, None]
        setup_bzr('/path')
        self.assertEqual(
            mp.call_args_list,
            [call(['whoami'], '/path'),
             call(['whoami', 'amulet@dummy-user.tld'], '/path'),
             call(['init'], '/path'),
             call(['config', 'add.maximum_file_size=0'], '/path'),
             ])


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

            # Patch w/o JUJU_REPOSITORY
            with patch.dict('amulet.charm.os.environ', {
                    'JUJU_REPOSITORY': ''}):
                CharmCache.get_charm('local:precise/mycharm')
                LocalCharm.assert_called_once_with('precise/mycharm')
                LocalCharm.reset_mock()

            # Patch w/JUJU_REPOSITORY
            with patch.dict('amulet.charm.os.environ', {
                    'JUJU_REPOSITORY': '~/charms'}):
                CharmCache.get_charm('local:precise/mycharm')
                LocalCharm.assert_called_once_with('~/charms/precise/mycharm')


class CharmCacheTest(unittest.TestCase):
    def test_init(self):
        c = CharmCache('mytestcharm')
        self.assertEqual(c.test_charm, 'mytestcharm')

    def test_getitem_service(self):
        c = CharmCache('mytestcharm')
        with patch.object(c, 'get_charm') as get_charm:
            charm = c['myservice']
            self.assertEqual(charm, get_charm.return_value)
            get_charm.assert_called_once_with('myservice', branch=None,
                                              series='precise')
            get_charm.reset_mock()
            charm2 = c['myservice']
            self.assertEqual(charm, charm2)
            self.assertFalse(get_charm.called)

    def test_getitem_testcharm(self):
        c = CharmCache('mytestcharm')
        with patch.object(c, 'get_charm') as get_charm:
            charm = c['mytestcharm']
            self.assertEqual(charm, get_charm.return_value)
            get_charm.assert_called_once_with(os.getcwd(), branch=None,
                                              series='precise')

    def test_fetch_service(self):
        c = CharmCache('mytestcharm')
        with patch.object(c, 'get_charm') as get_charm:
            charm = c.fetch('myservice')
            self.assertEqual(charm, get_charm.return_value)
            get_charm.assert_called_once_with('myservice', branch=None,
                                              series='precise')

        get_charm.reset_mock()
        charm2 = c['myservice']
        self.assertEqual(charm, charm2)
        self.assertFalse(get_charm.called)

    def test_fetch_charm(self):
        c = CharmCache('mytestcharm')
        with patch.object(c, 'get_charm') as get_charm:
            charm = c.fetch('myservice', 'anothercharm')
            self.assertEqual(charm, get_charm.return_value)
            get_charm.assert_called_once_with('anothercharm', branch=None, series='precise')

    def test_fetch_testcharm(self):
        c = CharmCache('mytestcharm')
        with patch.object(c, 'get_charm') as get_charm:
            charm = c.fetch('myservice', 'mytestcharm')
            self.assertEqual(charm, get_charm.return_value)
            get_charm.assert_called_once_with(os.getcwd(), branch=None,
                                              series='precise')


class IsBranchTest(unittest.TestCase):
    def setUp(self):
        self.charm_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.charm_dir)

    def test_bzr(self):
        os.mkdir(os.path.join(self.charm_dir, '.bzr'))
        self.assertTrue(is_branch(self.charm_dir))

    def test_no_control_dir(self):
        self.assertFalse(is_branch(self.charm_dir))
