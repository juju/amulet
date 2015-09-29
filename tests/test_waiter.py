"""Unit test for amulet.wait"""

import os
import unittest
import yaml
from amulet import wait
from amulet import waiter

from amulet.helpers import TimeoutError, JujuVersion
from .helper import JujuStatus

from mock import patch, Mock


class WaiterTest(unittest.TestCase):
    @patch('amulet.waiter.juju')
    def test_get_pyjuju_status(self, mock_check_output):
        mstatus = JujuStatus('juju')
        mstatus.add('wordpress')
        mstatus.add('mysql', state='pending')
        mock_check_output.return_value = str(mstatus)

        status = waiter._get_pyjuju_status('dummy')
        self.assertEqual(yaml.safe_load(str(mstatus)), status)
        mock_check_output.assert_called_with(
            ['status', '--format', 'yaml', '-e', 'dummy'])

    @patch('amulet.waiter.juju')
    def test_get_pyjuju_status_timeout(self, mj):
        mj.side_effect = [TimeoutError]
        self.assertRaises(TimeoutError, waiter._get_pyjuju_status)

    @patch('amulet.waiter.juju')
    def test_get_pyjuju_status_error(self, mj):
        mj.side_effect = [OSError(0, 'Non-zero exit')]
        self.assertRaises(Exception, waiter._get_pyjuju_status)

    @patch.object(waiter, '_get_pyjuju_status')
    def test_get_gojuju_status(self, mock_pyjuju_status):
        waiter._get_gojuju_status('dummy')
        mock_pyjuju_status.assert_called_with('dummy')

    def test_parse_unit_state(self):
        data = [{'life': 'dying'},
                {'agent-state': 'started',
                 'relations-error': {'key': ['unit']}},
                {'agent-state': 'pending'}]

        self.assertEqual('dying', waiter.get_state(data[0]))
        self.assertEqual(str(data[1]['relations-error']),
                         waiter.get_state(data[1]))
        self.assertEqual('pending', waiter.get_state(data[2]))

    @patch.object(waiter, 'status')
    @patch('amulet.helpers.JujuVersion')
    def test_state_py(self, jver, pyjuju_status):
        jver.side_effect = [JujuVersion(0, 7, 0, False)]
        mstatus = JujuStatus('juju')
        mstatus.add('test-charm')

        pyjuju_status.return_value = yaml.safe_load(str(mstatus))
        output = {'test-charm': {'0': 'started'}}
        self.assertEqual(output, waiter.state(juju_env='test'))

    @patch.object(waiter, 'status')
    @patch('amulet.helpers.JujuVersion')
    def test_state_go(self, jver, pyjuju_status):
        jver.side_effect = [JujuVersion(1, 11, 0, False)]
        mstatus = JujuStatus('juju')
        mstatus.add('test-charm')

        pyjuju_status.return_value = yaml.safe_load(str(mstatus))
        output = {'test-charm': {'0': 'started'}}
        self.assertEqual(output, waiter.state(juju_env='test'))

    @patch.object(waiter, 'status')
    @patch('amulet.helpers.JujuVersion')
    def test_state_specific_units(self, jver, pyjuju_status):
        jver.side_effect = [JujuVersion(0, 7, 0, False)]
        mstatus = JujuStatus('juju')
        mstatus.add('test-charm')
        mstatus.add('test-charm', state='pending')
        mstatus.add('test-charm')
        mstatus.add('test-charm-b')
        mstatus.add('test-charm-b')

        pyjuju_status.return_value = yaml.safe_load(str(mstatus))
        output = {'test-charm': {'1': 'pending'},
                  'test-charm-b': {'0': 'started', '1': 'started'}}
        self.assertEqual(output, waiter.state('test-charm/1', 'test-charm-b',
                                              juju_env='test'))

    @patch.object(waiter, 'status')
    @patch('amulet.helpers.JujuVersion')
    def test_state_subordinate_removal(self, jver, ms):
        jver.side_effect = [JujuVersion(1, 17, 0, False)]
        mstatus = JujuStatus('juju')
        mstatus.add('test-sub')
        mstatus.add('test-srv')
        mstatus.status['services']['test-sub'].pop('units', None)
        mstatus.status['services']['test-sub']['subordinate-to'] = 'test-srv'

        ms.return_value = yaml.safe_load(str(mstatus))
        output = {'test-srv': {'0': 'started'}}
        self.assertEqual(output, waiter.state(juju_env='test'))

    @patch.object(waiter, 'status')
    @patch('amulet.helpers.JujuVersion')
    def test_state_service_not_there(self, jver, pyjuju_status):
        jver.side_effect = [JujuVersion(0, 7, 0, False)]
        mstatus = JujuStatus('juju')

        pyjuju_status.return_value = yaml.safe_load(str(mstatus))
        self.assertRaises(ValueError, waiter.state, 'srvc', juju_env='test')

    @patch.object(waiter, 'status')
    @patch('amulet.helpers.JujuVersion')
    def test_state_timeout(self, jver, pyjuju_status):
        jver.side_effect = [JujuVersion(0, 7, 0, False)]

        pyjuju_status.side_effect = TimeoutError
        self.assertRaises(TimeoutError, waiter.state, juju_env='test')

    @patch.object(waiter, 'status')
    @patch('amulet.helpers.JujuVersion')
    def test_status_error(self, jver, pyjuju_status):
        jver.side_effect = [JujuVersion(0, 7, 0, False)]

        pyjuju_status.side_effect = Exception
        self.assertEqual({}, waiter.state(juju_env='test'))

    @patch('amulet.helpers.JujuVersion')
    def test_status_no_juju_env(self, jver):
        jver.side_effect = [JujuVersion(0, 7, 0, False)]

        self.assertRaises(KeyError, waiter.state)


class WaitTest(unittest.TestCase):
    @patch('amulet.waiter.state')
    def test_wait(self, waiter_status):
        waiter_status.return_value = {'test': {'0': 'started'}}

        self.assertTrue(wait(juju_env='dummy', timeout=1))
        waiter_status.assert_called_with(juju_env='dummy')

    @patch('amulet.waiter.raise_for_state')
    @patch('amulet.timeout')
    def test_wait_timeout(self, tout, waiter_status):
        waiter_status.side_effect = TimeoutError
        tout.side_effect = TimeoutError
        self.assertRaises(TimeoutError, wait, juju_env='dummy')

    @patch('amulet.waiter.state')
    @patch.dict('os.environ', {'JUJU_ENV': 'testing-env'})
    def test_wait_juju_env(self, waiter_status):
        waiter_status.return_value = {'test': {'0': 'started'}}
        wait()
        waiter_status.assert_called_with(juju_env='testing-env')

    @patch('amulet.waiter.state')
    @patch('amulet.default_environment')
    @patch.dict('os.environ', {'JUJU_HOME': '/tmp/juju-home'})
    def test_wait_default_juju_env(self, default_env, waiter_status):
        if not os.path.exists('/tmp/juju-home'):
            os.makedirs('/tmp/juju-home')
        envyaml = yaml.dump({'default': 'testing-default-env',
                             'environments': {'testing-default-env':
                                              {'type': 'local'}}})
        with open('/tmp/juju-home/environments.yaml', 'w') as f:
            f.write(envyaml)

        waiter_status.return_value = {'test': {'0': 'started'}}
        default_env.return_value = 'testing-default-env'
        try:
            wait()
        finally:
            os.remove('/tmp/juju-home/environments.yaml')
            os.removedirs('/tmp/juju-home')

        waiter_status.assert_called_with(juju_env='testing-default-env')

    @patch('amulet.waiter.state')
    def test_wait_not_ready(self, waiter_status):
        waiter_status.side_effect = [{'test': {'0': 'pending'}},
                                     {'test': {'0': 'started'}}]

        self.assertTrue(wait(juju_env='dummy', timeout=1))

    @patch('amulet.helpers.juju', Mock(return_value='status'))
    @patch('amulet.waiter.state')
    def test_wait_exception(self, waiter_status):
        waiter_status.side_effect = waiter.StateError

        self.assertRaises(TimeoutError, wait, juju_env='dummy', timeout=0.01)


class StatusTest(unittest.TestCase):
    @patch('amulet.waiter._get_gojuju_status')
    def test_status_go(self, mpy):
        waiter.status('gojuju')
        mpy.assert_called_with('gojuju')

    @patch('amulet.waiter._get_pyjuju_status')
    @patch('amulet.waiter.JujuVersion')
    def test_status_py(self, mj, mpy):
        mj.side_effect = [JujuVersion(0, 7, 0, False)]
        waiter.status('pyjuju')
        mpy.assert_called_with('pyjuju')

    def test_status_noenv(self):
        self.assertRaises(Exception, waiter.status)

    @patch('amulet.waiter._get_gojuju_status')
    def test_wait_timeout(self, mpy):
        mpy.side_effect = [TimeoutError]
        self.assertRaises(TimeoutError, waiter.status, 'godummy')

    @patch('amulet.waiter._get_gojuju_status')
    def test_wait_exception(self, mpy):
        mpy.side_effect = [Exception]
        self.assertRaises(Exception, waiter.status, 'godummy')
