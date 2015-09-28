"""Unit test for amulet.wait"""

import unittest
import sys
import yaml
import time

from amulet.helpers import (
    JujuVersion,
    environments,
    default_environment,
    juju,
    raise_status,
    timeout_gen,
    TimeoutError,
)

from mock import patch, Mock

RAW_ENVIRONMENTS_YAML = '''
default: gojuju
environments:
  gojuju:
    type: cloud
    access-key: xxx
    secret-key: yyy
    control-bucket: gojuju-xyxyz
    admin-secret: zyxyx
    default-series: world
  pyjuju:
    type: cloud
    access-key: xxx
    secret-key: yyy
    control-bucket: juju-xyxyz
    admin-secret: zyxyxy
    default-series: world
    juju-origin: ppa
    ssl-hostname-verification: true'''


class HelpersTest(unittest.TestCase):
    @patch('amulet.helpers.juju')
    def test_jujuversion_go(self, mj):
        mj.side_effect = ['1.2.3-series-xxx']
        version = JujuVersion()

        self.assertEqual(version.major, 1)
        self.assertEqual(version.minor, 2)
        self.assertEqual(version.patch, 3)
        self.assertEqual(str(version), '1.2.3')

        mj.assert_called_with(['version'])

    @patch('amulet.helpers.juju')
    def test_jujuversion_py(self, mj):
        mj.side_effect = [OSError('Non-zero exit'), 'juju 8.6']
        version = JujuVersion()

        self.assertEqual(version.major, 8)
        self.assertEqual(version.minor, 6)
        self.assertEqual(version.patch, None)
        self.assertEqual(str(version), '8.6')

        mj.assert_called_with(['--version'])

    @patch('amulet.helpers.juju')
    def test_jujuversion_malformed(self, mj):
        mj.return_value = '1.2.3.45'
        version = JujuVersion()

        self.assertEqual(version.major, 1)
        self.assertEqual(version.minor, 2)
        self.assertEqual(version.patch, 3)
        self.assertEqual(str(version), '1.2.3')

        mj.assert_called_once_with(['version'])

    @patch('os.path.isfile')
    @patch('builtins.open' if sys.version_info > (3,) else '__builtin__.open')
    def test_environments(self, mock_open, mock_exists):
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = Mock()
        mock_open.return_value.read.return_value = RAW_ENVIRONMENTS_YAML
        mock_exists.return_value = True

        envs = environments()
        self.assertEqual(yaml.safe_load(RAW_ENVIRONMENTS_YAML), envs)

    @patch('os.path.isfile')
    def test_environments_noenv(self, mock_exists):
        mock_exists.return_value = False

        self.assertRaises(IOError, environments)

    @patch('amulet.helpers.environments')
    def test_default_environment(self, menvironments):
        menvironments.return_value = yaml.safe_load(RAW_ENVIRONMENTS_YAML)
        default = default_environment()
        self.assertEqual('gojuju', default)

    @patch('amulet.helpers.environments')
    def test_default_environment_no_default(self, menvironments):
        environments_yaml = """
        environments:
          gojuju1:
            type: cloud
            access-key: xxx
            secret-key: yyy
            control-bucket: gojuju-xyxyz
            admin-secret: zyxyx
            default-series: world"""
        menvironments.return_value = yaml.safe_load(environments_yaml)
        self.assertEqual('gojuju1', default_environment())

    @patch('amulet.helpers.environments')
    def test_default_environment_no_default_multi_fail(self, menvironments):
        envs = yaml.safe_load(RAW_ENVIRONMENTS_YAML)
        del envs['default']
        menvironments.return_value = envs

        self.assertRaises(ValueError, default_environment)

    @patch('amulet.helpers.juju', Mock(return_value='status'))
    def test_timeout_gen(self):
        def case(t):
            for i in timeout_gen(t):
                time.sleep(0.2)
                if i == 1:
                    return
        self.assertRaises(TimeoutError, case, 0.1)
        case(0.5)


class JujuTest(unittest.TestCase):
    def test_juju(self):
        self.assertEqual(str(JujuVersion()), juju(['version']).split('-')[0])

    @patch('amulet.helpers.subprocess.Popen')
    def test_juju_oserror(self, mp):
        mp.side_effect = [OSError(1, 'Command Failed')]
        self.assertRaisesRegexp(OSError, 'Command Failed', juju, ['version'])


class RaiseStatusTest(unittest.TestCase):
    @patch('amulet.helpers.sys.exit')
    def test_raise_status(self, me):
        raise_status(0)
        me.assert_called_with(0)

    @patch('amulet.helpers.sys.exit')
    @patch('builtins.print' if sys.version_info > (3,) else '__builtin__.print')
    def test_raise_status_msg(self, mp, me):
        raise_status(100, 'Hello World')
        mp.assert_called_with('Hello World')
        me.assert_called_with(100)
