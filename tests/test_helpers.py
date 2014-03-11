"""Unit test for amulet.wait"""

import unittest
import sys
import yaml

from amulet.helpers import (
    JujuVersion,
    environments,
    default_environment,
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
    @patch('subprocess.check_output')
    def test_jujuversion_go(self, mock_check_output):
        mock_check_output.side_effect = ['1.2.3-series-xxx']
        version = JujuVersion()

        self.assertEqual(version.major, 1)
        self.assertEqual(version.minor, 2)
        self.assertEqual(version.patch, 3)
        self.assertEqual(str(version), '1.2.3')

        mock_check_output.assert_called_with(['juju', 'version'])

    @patch('subprocess.check_output')
    def test_jujuversion_py(self, mcheck_output):
        mcheck_output.side_effect = [Exception('Non-zero exit'), 'juju 8.6']
        version = JujuVersion()

        self.assertEqual(version.major, 8)
        self.assertEqual(version.minor, 6)
        self.assertEqual(version.patch, 0)
        self.assertEqual(str(version), '8.6.0')

        mcheck_output.assert_called_with(['juju', '--version'], stderr=-2)

    @patch('subprocess.check_output')
    def test_jujuversion_malformed(self, mcheck_output):
        mcheck_output.return_value = '1.2.3.45'
        version = JujuVersion()

        self.assertEqual(version.major, 1)
        self.assertEqual(version.minor, 2)
        self.assertEqual(version.patch, 3)
        self.assertEqual(str(version), '1.2.3')

        mcheck_output.assert_called_once_with(['juju', 'version'])

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
