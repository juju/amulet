import re
import unittest
import yaml
from datetime import datetime
from copy import deepcopy

from amulet.sentry import (
    Talisman,
    UnitSentry,
    StatusMessageMatcher,
)
from amulet.helpers import (
    TimeoutError,
    UnsupportedError,
)
from mock import patch, Mock


mock_status = yaml.load("""\
machines:
  "0":
    agent-state: started
    agent-version: 1.24.6.1
    dns-name: localhost
    instance-id: localhost
    series: trusty
    state-server-member-status: has-vote
  "1":
    agent-state: started
    instance-id: johnsca-local-machine-1
    series: trusty
    hardware: arch=amd64
  "2":
    agent-state: started
    instance-id: johnsca-local-machine-1
    series: trusty
    hardware: arch=amd64
  "3":
    agent-state: pending
    instance-id: johnsca-local-machine-1
    series: trusty
    hardware: arch=amd64
services:
  meteor:
    units:
      meteor/0:
        public-address: 10.0.3.152
        workload-status:
          current: active
          message: ready
          since: 24 Sep 2015 16:44:44-04:00
        agent-status:
          current: idle
          since: 24 Sep 2015 16:44:44-04:00
        machine: "1"
      meteor/1:
        public-address: 10.0.3.177
        workload-status:
          current: active
          message: ready
          since: 24 Sep 2015 16:44:44-04:00
        agent-status:
          current: idle
          since: 24 Sep 2015 16:44:44-04:00
        machine: "2"
        subordinates:
          rsyslog-forwarder/0:
            public-address: 10.0.3.115
            workload-status:
              current: active
              message: rsyslog
  relation-sentry:
    units:
      relation-sentry/0:
        public-address: 10.0.3.92
  rsyslog-forwarder:
    charm: cs:trusty/rsyslog-forwarder
    subordinate-to:
    - meteor
    relations:
      juju-info:
      - meteor
  pending:
    units:
      pending/0:
        public-address: 10.0.3.152
        workload-status:
          current: unknown
          since: 24 Sep 2015 16:44:44-04:00
        agent-status:
          current: allocating
          since: 24 Sep 2015 16:44:44-04:00
        machine: "3"
  nopublic:
    units:
      nopublic/0:
        workload-status:
          current: maintainence
          message: working
          since: 24 Sep 2015 16:44:44-04:00
        agent-status:
          current: executing
          since: 24 Sep 2015 16:44:44-04:00
        machine: "2"
  errord:
    units:
      errord/0:
        public-address: 10.0.3.152
        workload-status:
          current: error
          message: 'hook failed: "install"'
          since: 24 Sep 2015 16:44:44-04:00
        agent-status:
          current: idle
          since: 24 Sep 2015 16:44:44-04:00
        machine: "2"
  old:
    units:
      old/0:
        public-address: 10.0.3.152
        agent-state: started
        machine: "2"
  olderrord:
    units:
      olderrord/0:
        public-address: 10.0.3.152
        agent-state: error
        agent-state-info: 'hook failed: "install"'
        machine: "2"
  ubuntu:
    charm: cs:trusty/ubuntu-4
    exposed: false
    service-status:
      current: unknown
      message: Waiting for agent initialization to finish
      since: 30 Sep 2015 16:44:09-04:00
    relations:
      juju-info:
      - sub
      - subpend
    units:
      ubuntu/0:
        workload-status:
          current: unknown
          since: 24 Sep 2015 16:44:44-04:00
        agent-status:
          current: started
          since: 24 Sep 2015 16:44:44-04:00
        agent-state: pending
        machine: "2"
        subordinates:
          sub/0:
            public-address: 10.0.3.115
            agent-status:
              current: started
              since: 24 Sep 2015 16:44:44-04:00
  sub:
    charm: cs:trusty/sub-1
    subordinate-to:
    - ubuntu
    relations:
      juju-info:
      - ubuntu
  subpend:
    charm: cs:trusty/subpend-1
    subordinate-to:
    - ubuntu
    relations:
      juju-info:
      - ubuntu
  unsub:
    charm: cs:trusty/unsub-1
""")


class TalismanTest(unittest.TestCase):
    timeout = 0.01

    @patch.object(Talisman, 'wait_for_status')
    @patch.object(UnitSentry, 'upload_scripts')
    @patch('amulet.sentry.helpers.default_environment')
    def test_init(self, default_env, upload_scripts, wait_for_status):
        default_env.return_value = 'local'
        wait_for_status.return_value = mock_status

        sentry = Talisman(['meteor'], timeout=self.timeout)

        self.assertTrue('meteor/0' in sentry.unit)
        self.assertTrue('meteor/1' in sentry.unit)

    @patch.object(Talisman, 'wait_for_status')
    @patch.object(UnitSentry, 'upload_scripts')
    @patch('amulet.sentry.helpers.default_environment')
    def test_getitem(self, default_env, upload_scripts, wait_for_status):
        default_env.return_value = 'local'
        wait_for_status.return_value = mock_status

        sentry = Talisman(['meteor'], timeout=self.timeout)

        self.assertEqual(sentry['meteor/0'], sentry.unit['meteor/0'])
        self.assertEqual(sentry['meteor'], list(sentry.unit.values()))

    @patch.object(Talisman, 'wait_for_status')
    @patch.object(UnitSentry, 'upload_scripts')
    @patch('amulet.sentry.helpers.default_environment')
    def test_subordinate(self, default_env, upload_scripts, wait_for_status):
        default_env.return_value = 'local'
        wait_for_status.return_value = mock_status

        sentry = Talisman(['meteor', 'rsyslog-forwarder'], timeout=self.timeout)

        self.assertTrue('rsyslog-forwarder/0' in sentry.unit)

    @patch.object(Talisman, '__init__', Mock(return_value=None))
    @patch('amulet.helpers.juju', Mock(return_value='status'))
    @patch('amulet.waiter.status')
    def test_wait_for_status(self, status):
        status.return_value = mock_status
        talisman = Talisman([], timeout=self.timeout)

        talisman.wait_for_status('env', ['meteor'], self.timeout)
        talisman.wait_for_status('env', ['old'], self.timeout)
        talisman.wait_for_status('env', ['sub'], self.timeout)
        talisman.wait_for_status('env', ['unsub'], self.timeout)

        self.assertRaises(TimeoutError, talisman.wait_for_status, 'env', ['pending'], self.timeout)
        self.assertRaises(TimeoutError, talisman.wait_for_status, 'env', ['nopublic'], self.timeout)
        self.assertRaisesRegexp(Exception, r'Error on unit.*hook failed',
                                talisman.wait_for_status, 'env', ['errord'], self.timeout)
        self.assertRaisesRegexp(Exception, r'Error on unit.*hook failed',
                                talisman.wait_for_status, 'env', ['olderrord'], self.timeout)
        self.assertRaises(TimeoutError, talisman.wait_for_status, 'env', ['subpend'], self.timeout)

    @patch('amulet.helpers.juju', Mock(return_value='status'))
    @patch('amulet.helpers.default_environment', Mock())
    @patch.object(UnitSentry, 'upload_scripts', Mock())
    @patch.object(UnitSentry, 'juju_agent')
    @patch('amulet.waiter.status')
    def test_wait(self, _status, juju_agent):
        status = _status.return_value = deepcopy(mock_status)

        def set_state(which, key, value):
            status['services']['meteor']['units']['meteor/0'][which][key] = value

        t = Talisman(['meteor'], timeout=self.timeout)
        t.wait(self.timeout)

        set_state('workload-status', 'current', 'unknown')
        t.wait(self.timeout)

        set_state('workload-status', 'current', 'blocked')
        t.wait(self.timeout)

        set_state('workload-status', 'current', 'active')
        set_state('agent-status', 'current', 'executing')
        self.assertRaises(TimeoutError, t.wait, self.timeout)

        set_state('agent-status', 'current', 'idle')
        set_state('agent-status', 'since', datetime.now().strftime('%d %b %Y %H:%M:%S'))
        self.assertRaises(TimeoutError, t.wait, self.timeout)

        t = Talisman(['old'], timeout=self.timeout)
        juju_agent.return_value = None
        self.assertRaises(TimeoutError, t.wait, self.timeout)

        juju_agent.return_value = {'hook': 'foo'}
        self.assertRaises(TimeoutError, t.wait, self.timeout)

        juju_agent.return_value = {}
        t.wait(self.timeout)

    @patch('amulet.helpers.juju', Mock(return_value='status'))
    @patch('amulet.helpers.default_environment', Mock())
    @patch('amulet.waiter.status')
    def test_wait_for_messages(self, _status):
        status = _status.return_value = deepcopy(mock_status)
        t = Talisman([], timeout=self.timeout)

        def set_status(unit, message):
            service = unit.split('/')[0]
            status['services'][service]['units'][unit]['workload-status']['message'] = message

        t.wait_for_messages({'meteor': 'ready'}, self.timeout)
        t.wait_for_messages({'meteor': re.compile('r..dy')}, self.timeout)
        t.wait_for_messages({'meteor': {'ready'}}, self.timeout)
        t.wait_for_messages({'meteor': re.compile('ready|ok')}, self.timeout)
        self.assertRaises(TimeoutError, t.wait_for_messages, {'meteor': {'ready', 'ok'}}, self.timeout)
        self.assertRaises(TimeoutError, t.wait_for_messages, {'meteor': ['ready', 'ok']}, self.timeout)

        set_status('meteor/0', 'ok')
        self.assertRaises(TimeoutError, t.wait_for_messages, {'meteor': 'ready'}, self.timeout)
        self.assertRaises(TimeoutError, t.wait_for_messages, {'meteor': re.compile('r..dy')}, self.timeout)
        t.wait_for_messages({'meteor': {'ready'}}, self.timeout)
        t.wait_for_messages({'meteor': re.compile('ready|ok')}, self.timeout)
        t.wait_for_messages({'meteor': {'ready', 'ok'}}, self.timeout)
        t.wait_for_messages({'meteor': ['ready', 'ok']}, self.timeout)

        set_status('meteor/1', 'ok')
        self.assertRaises(TimeoutError, t.wait_for_messages, {'meteor': 'ready'}, self.timeout)
        self.assertRaises(TimeoutError, t.wait_for_messages, {'meteor': re.compile('r..dy')}, self.timeout)
        self.assertRaises(TimeoutError, t.wait_for_messages, {'meteor': {'ready'}}, self.timeout)
        t.wait_for_messages({'meteor': re.compile('ready|ok')}, self.timeout)
        self.assertRaises(TimeoutError, t.wait_for_messages, {'meteor': {'ready', 'ok'}}, self.timeout)
        self.assertRaises(TimeoutError, t.wait_for_messages, {'meteor': ['ready', 'ok']}, self.timeout)

        set_status('meteor/0', 'ready')
        status['services']['meteor']['units']['meteor/2'] = {
            'workload-status': {
                'current': 'active',
                'message': 'working',
            },
        }
        t.wait_for_messages({'meteor': {'ready', 'ok'}})
        self.assertRaises(TimeoutError, t.wait_for_messages, {'meteor': ['ready', 'ok']}, self.timeout)
        self.assertRaises(TimeoutError, t.wait_for_messages, {'meteor': ['ready', 'ok', 'ready']}, self.timeout)

        t.wait_for_messages({'rsyslog-forwarder': 'rsyslog'}, self.timeout)
        self.assertRaises(TimeoutError, t.wait_for_messages, {'rsyslog-forwarder': 'ready'}, self.timeout)

        self.assertRaises(UnsupportedError, t.wait_for_messages, {'old': 'ready'}, self.timeout)


class TestStatusMessageMatcher(unittest.TestCase):
    def test_check(self):
        m = StatusMessageMatcher()
        m.check_messages = Mock()
        m.check_set = Mock()
        m.check_list = Mock()

        m.check('ready', ['ready'])
        m.check(re.compile('ready'), ['ready'])
        self.assertEqual(m.check_messages.call_count, 2)

        m.check({'ready'}, ['ready'])
        self.assertEqual(m.check_set.call_count, 1)

        m.check(['ready'], ['ready'])
        m.check(('ready',), ['ready'])
        self.assertEqual(m.check_list.call_count, 2)

    def test_check_messages(self):
        m = StatusMessageMatcher()

        assert m.check_messages('ready', ['ready'])
        assert m.check_messages('ready', ['ready', 'ready'])
        assert not m.check_messages('ready', ['ready', 'ok'])
        assert not m.check_messages('ready', [])

    def test_check_set(self):
        m = StatusMessageMatcher()

        assert m.check_set({'ready'}, ['ready'])
        assert m.check_set({'ready'}, ['ready', 'ok'])
        assert m.check_set({'ready', 'ok'}, ['ready', 'ok'])
        assert not m.check_set({'ready', 'ok'}, ['ready', 'ready'])
        assert not m.check_set({'ok'}, ['ready', 'ready'])
        assert not m.check_set({'ready'}, [])

    def test_check_list(self):
        m = StatusMessageMatcher()
        r = re.compile

        assert m.check_list(['ready'], ['ready'])
        assert not m.check_list(['ready', 'ready'], ['ready'])  # too few
        assert not m.check_list(['ready'], ['ready', 'ready'])  # too many
        assert m.check_list(['ready', 'ready', 'ok'], ['ready', 'ok', 'ready'])
        assert not m.check_list(['ready', 'ready', 'ok'], ['ready', 'ok', 'ok'])
        assert m.check_list([r('ready(ish)?')], ['ready'])
        assert m.check_list([r('ready(ish)?')], ['readyish'])
        assert m.check_list([r('ready(ish)?'), 'ready'], ['ready', 'readyish'])  # ambiguous-ish
        assert m.check_list([r('ready(ish)?'), 'ready'], ['readyish', 'ready'])  # ambiguous-ish

    def test_check_message(self):
        m = StatusMessageMatcher()
        r = re.compile
        self.assertEqual(0, m.check_message('bar', 'foo'))
        self.assertEqual(3, m.check_message('foo', 'foo'))
        self.assertEqual(3, m.check_message(r('foo'), 'foo'))
        self.assertEqual(3, m.check_message(r('foo'), 'foobar'))
        self.assertEqual(3, m.check_message(r('f..'), 'foo'))
        self.assertEqual(0, m.check_message(r('b..'), 'foo'))
