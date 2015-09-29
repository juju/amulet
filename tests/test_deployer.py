"""Unit test for amulet.wait"""

import os
import unittest
import json
import shutil
import tempfile
import yaml

from amulet import Deployment
from amulet.deployer import get_charm_name
from amulet.sentry import UnitSentry
from mock import patch, MagicMock, call
from collections import OrderedDict

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


class DeployerTests(unittest.TestCase):
    def test_init(self):
        d = Deployment(juju_env='gojuju')
        self.assertEqual('precise', d.series)
        self.assertEqual('gojuju', d.juju_env)
        self.assertEqual({}, d.services)
        self.assertEqual([], d.relations)

    def test_load(self):
        d = Deployment(juju_env='gojuju')
        schema = '{"mybundle": {"series": "raring", "services": {"wordpress": \
                  {"branch": "lp:~charmers/charms/precise/wordpress/trunk", \
                  "expose": true}, "mysql": {"options": {"tuning": \
                  "fastest"}, "constraints": "mem=2G cpu-cores=2", \
                  "branch": "lp:~charmers/charms/precise/mysql/trunk"}}, \
                  "relations": [["mysql:db", "wordpress:db"]]}}'
        dmap = json.loads(schema)
        with patch.object(d, 'add') as add:
            with patch.object(d, 'configure') as configure:
                with patch.object(d, 'expose') as expose:
                    d.load(dmap)
        self.assertEqual(d.juju_env, 'gojuju')
        self.assertEqual(dmap['mybundle']['relations'], d.relations)
        self.assertEqual(dmap['mybundle']['series'], d.series)
        add.assert_has_calls([
            call('wordpress',
                 placement=None,
                 series='raring',
                 units=1,
                 branch='lp:~charmers/charms/precise/wordpress/trunk',
                 constraints=None,
                 charm=None),
            call('mysql',
                 placement=None,
                 series='raring',
                 units=1,
                 branch='lp:~charmers/charms/precise/mysql/trunk',
                 constraints={'mem': '2G', 'cpu-cores': '2'},
                 charm=None)],
            any_order=True
        )
        configure.assert_has_calls([
            call('mysql', {'tuning': 'fastest'}),
        ])
        expose.assert_has_calls([
            call('wordpress'),
        ])

    @patch('amulet.charm.CharmCache.get_charm')
    def test_add(self, mcharm):
        charm = mcharm.return_value
        charm.subordinate = False
        charm.code_source = {'location':
                             'lp:~charmers/charms/precise/charm/trunk'}
        charm.url = 'cs:precise/charm'

        d = Deployment(juju_env='gojuju')
        d.add('charm')
        self.assertEqual({'charm': {'charm': 'cs:precise/charm',
                                    'num_units': 1}}, d.services)

    @patch('amulet.charm.CharmCache.get_charm')
    def test_add_branch(self, mcharm):
        charm = mcharm.return_value
        charm.subordinate = False
        charm.code_source = {'location': 'lp:~foo/charms/precise/baz/trunk'}
        charm.url = None

        d = Deployment(juju_env='gojuju')
        d.add('bar', 'cs:~foo/baz')
        self.assertEqual({'bar': {'branch': 'lp:~foo/charms/precise/baz/trunk',
                                  'num_units': 1}}, d.services)

    @patch('amulet.charm.CharmCache.get_charm')
    def test_add_units(self, mcharm):
        charm = mcharm.return_value
        charm.subordinate = False
        charm.code_source = {'location': 'lp:charms/charm'}
        charm.url = None

        d = Deployment(juju_env='gojuju')
        d.add('charm', units=2)
        self.assertEqual({'charm': {'branch': 'lp:charms/charm',
                                    'num_units': 2}}, d.services)

    @patch('amulet.charm.CharmCache.get_charm')
    def test_add_constraints(self, mcharm):
        charm = mcharm.return_value
        charm.subordinate = False
        charm.code_source = {'location': 'lp:charms/charm'}
        charm.url = None

        d = Deployment(juju_env='gojuju')
        d.add('charm', units=2, constraints=OrderedDict([
            ("cpu-power", 0),
            ("cpu-cores", 4),
            ("mem", "512M")
        ]))

        self.assertEqual({'charm': {'branch': 'lp:charms/charm',
                                    'constraints':
                                    'cpu-power=0 cpu-cores=4 mem=512M',
                                    'num_units': 2}}, d.services)

    def _make_mock_status(self, d):
        def _mock_status(juju_env):
            status = dict(services={}, machines={})
            total_units = 1
            for service in d.services:
                status['services'][service] = dict(units={})
                for unit in range(d.services[service].get('num_units', 1)):
                    total_units += 1
                    status['services'][service]['units'][
                        '{}/{}'.format(service, unit)] = {
                        'agent-state': 'started',
                        'public-address': '10.0.3.{}'.format(total_units),
                        'machine': str(total_units)}
                    status['machines'][str(total_units)] = {
                        'agent-state': 'started',
                    }
            status['services']['relation-sentry'] = {
                'units': {
                    'relation-sentry/0': {
                        'agent-state': 'started',
                        'public-address': '10.0.3.1',
                        'machine': str(total_units+1)}}}
            status['machines'][str(total_units+1)] = {
                'agent-state': 'started',
            }
            return status
        return _mock_status

    @patch.object(UnitSentry, 'upload_scripts')
    @patch('amulet.helpers.environments')
    @patch('amulet.sentry.waiter.status')
    @patch('amulet.deployer.subprocess')
    @patch('amulet.charm.CharmCache.get_charm')
    def test_add_unit(self, mcharm, subprocess, waiter_status, environments,
                      upload_scripts):
        charm = mcharm.return_value
        charm.subordinate = False
        charm.code_source = {'location': 'lp:charms/charm'}
        charm.url = None
        charm.series = 'precise'

        environments.return_value = yaml.safe_load(RAW_ENVIRONMENTS_YAML)

        d = Deployment(juju_env='gojuju')

        waiter_status.side_effect = self._make_mock_status(d)
        d.add('charm', units=1)
        d.setup()
        with patch('amulet.deployer.juju') as j:
            d.add_unit('charm')
            j.assert_called_with(['add-unit', 'charm', '-n', '1'])
        self.assertTrue('charm/1' in d.sentry.unit)
        self.assertEqual(2, d.services['charm']['num_units'])

    @patch.object(UnitSentry, 'upload_scripts')
    @patch('amulet.helpers.environments')
    @patch('amulet.sentry.waiter.status')
    @patch('amulet.deployer.subprocess')
    @patch('amulet.charm.CharmCache.get_charm')
    def test_add_unit_target(self, mcharm, subprocess, waiter_status,
                             environments, upload_scripts):
        """
        If target is given to Deployment.add_unit(), the 'juju' call
        will includde --to to make the unit be added to the given
        target.
        """
        charm = mcharm.return_value
        charm.subordinate = False
        charm.code_source = {'location': 'lp:charms/charm'}
        charm.url = None
        charm.series = 'precise'

        environments.return_value = yaml.safe_load(RAW_ENVIRONMENTS_YAML)

        d = Deployment(juju_env='gojuju')

        waiter_status.side_effect = self._make_mock_status(d)
        d.add('charm', units=1)
        d.setup()
        with patch('amulet.deployer.juju') as j:
            d.add_unit('charm', target='lxc:0')
            j.assert_called_with(
                ['add-unit', 'charm', '-n', '1', '--to', 'lxc:0'])

    @patch.object(UnitSentry, 'upload_scripts')
    @patch('amulet.helpers.environments')
    @patch('amulet.sentry.waiter.status')
    @patch('amulet.deployer.subprocess')
    @patch('amulet.charm.CharmCache.get_charm')
    def test_add_unit_error(self, mcharm, subprocess, waiter_status,
                            environments, upload_scripts):
        def mock_unit_error(f, service, unit_name):
            def _mock_unit_error(juju_env):
                status = f(juju_env)
                unit = status['services'][service]['units'].get(unit_name)
                if not unit:
                    return status
                unit['agent-state'] = 'error'
                unit['agent-state-info'] = 'hook failed: install'
                return status
            return _mock_unit_error

        charm = mcharm.return_value
        charm.subordinate = False
        charm.code_source = {'location': 'lp:charms/charm'}
        charm.url = None
        charm.series = 'precise'

        environments.return_value = yaml.safe_load(RAW_ENVIRONMENTS_YAML)

        d = Deployment(juju_env='gojuju')
        waiter_status.side_effect = mock_unit_error(
            self._make_mock_status(d), 'charm', 'charm/1')
        d.add('charm', units=1)
        d.setup()
        with patch('amulet.deployer.juju'):
            self.assertRaisesRegexp(
                Exception, 'Error on unit charm/1: hook failed: install',
                d.add_unit, 'charm')

    @patch('amulet.charm.CharmCache.get_charm')
    def test_remove_unit(self, get_charm):
        d = Deployment(juju_env='gojuju')
        d.add('charm')
        patcher = patch.object(d, 'sentry', MagicMock(unit={'charm/0': 1}))
        self.addCleanup(patcher.stop)
        sentry = patcher.start()
        d.deployed = True
        with patch('amulet.deployer.juju') as juju:
            d.remove_unit('charm/0')
            juju.assert_called_once_with(['remove-unit', 'charm/0'])
        self.assertFalse('charm/0' in sentry.unit)
        self.assertEqual(0, d.services['charm']['num_units'])

    @patch('amulet.charm.CharmCache.get_charm')
    def test_remove_service(self, get_charm):
        d = Deployment(juju_env='gojuju')
        d.add('charm')
        patcher = patch.object(d, 'sentry', MagicMock(unit={'charm/0': 1}))
        self.addCleanup(patcher.stop)
        sentry = patcher.start()
        d.deployed = True
        d.relations = [('charm:rel', 'another:rel')]
        with patch('amulet.deployer.juju') as juju:
            d.remove_service('charm')
            juju.assert_called_once_with(['remove-service', 'charm'])
        self.assertFalse('charm/0' in sentry.unit)
        self.assertFalse('charm' in d.services)
        self.assertEqual(0, len(d.relations))

    @patch('amulet.charm.CharmCache.get_charm')
    def test_remove(self, get_charm):
        d = Deployment(juju_env='gojuju')
        d.add('charm1')
        d.add('charm2')
        p1 = patch.object(d, 'remove_unit')
        p2 = patch.object(d, 'remove_service')
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)
        remove_unit = p1.start()
        remove_service = p2.start()
        with patch('amulet.deployer.juju'):
            d.remove('charm1/0', 'charm2')
            remove_unit.assert_called_once_with('charm1/0')
            remove_service.assert_called_once_with('charm2')

    @patch('amulet.charm.CharmCache.get_charm')
    def test_remove_aliases(self, get_charm):
        d = Deployment
        self.assertEqual(d.destroy_unit, d.remove_unit)
        self.assertEqual(d.destroy_service, d.remove_service)
        self.assertEqual(d.destroy, d.remove)

    @patch('amulet.charm.CharmCache.get_charm')
    def test_add_error(self, mcharm):
        d = Deployment(juju_env='gojuju')
        d.add('bar')
        self.assertRaises(ValueError, d.add, 'bar')

    @patch('amulet.charm.CharmCache.get_charm')
    def test_relate(self, mcharm):
        a = mcharm.return_value
        a.provides = {'f': {'interface': 'test'}}
        a.requires = {'b': {'interface': 'test'}}

        d = Deployment(juju_env='gojuju')
        d.add('bar')
        d.add('foo')
        d.relate('foo:f', 'bar:b')
        self.assertEqual(d.relations, [['foo:f', 'bar:b']])

    def test_relate_too_few(self):
        d = Deployment(juju_env='gojuju')
        self.assertRaises(LookupError, d.relate, 'foo:f')

    def test_relate_no_relation(self):
        d = Deployment(juju_env='gojuju')
        self.assertRaises(ValueError, d.relate, 'foo', 'bar:a')

    @patch('amulet.charm.CharmCache.get_charm')
    def test_relate_relation_nonexist(self, mcharm):
        d = Deployment(juju_env='gojuju')
        d.add('bar')
        d.add('foo')

        self.assertRaises(ValueError, d.relate, 'foo:f', 'bar:b')

    def test_relate_not_deployed(self):
        d = Deployment(juju_env='gojuju')
        self.assertRaises(ValueError, d.relate, 'foo:f', 'bar:a')

    @patch('amulet.charm.CharmCache.get_charm')
    def test_configure(self, mcharm):
        charm = mcharm.return_value
        charm.subordinate = False
        charm.code_source = {'location':
                             'lp:~charmers/charms/precise/wordpress/trunk'}
        charm.url = 'cs:precise/wordpress'

        d = Deployment(juju_env='gojuju')
        d.add('wordpress')
        d.configure('wordpress', {'tuning': 'optimized'})
        d.configure('wordpress', {'wp-content': 'f', 'port': 100})
        self.assertEqual({'wordpress':
                          {'charm': 'cs:precise/wordpress',
                           'num_units': 1,
                           'options': {'tuning': 'optimized',
                                       'wp-content': 'f',
                                       'port': 100}}}, d.services)

    def test_configure_not_deployed(self):
        d = Deployment(juju_env='gojuju')
        self.assertRaises(ValueError, d.configure, 'wordpress',
                          {'tuning': 'optimized'})

    @patch('amulet.charm.CharmCache.get_charm')
    def test_expose(self, mcharm):
        charm = mcharm.return_value
        charm.subordinate = False
        charm.code_source = {'location':
                             'lp:~charmers/charms/precise/wordpress/trunk'}
        charm.url = None

        d = Deployment(juju_env='gojuju')
        d.add('wordpress')
        d.expose('wordpress')
        self.assertEqual(
            {'wordpress':
                {'branch': 'lp:~charmers/charms/precise/wordpress/trunk',
                 'num_units': 1,
                 'expose': True}}, d.services)

    def test_expose_not_deployed(self):
        d = Deployment(juju_env='gojuju')
        self.assertRaises(ValueError, d.expose, 'wordpress')

    @patch('amulet.charm.CharmCache.get_charm')
    def test_schema(self, mcharm):
        wpmock = MagicMock()
        mysqlmock = MagicMock()
        wpmock.subordinate = False
        wpmock.code_source = {'location':
                              'lp:~charmers/charms/precise/wordpress/trunk'}
        wpmock.requires = {'db': {'interface': 'mysql'}}
        wpmock.url = None
        mysqlmock.subordinate = False
        mysqlmock.code_source = {'location':
                                 'lp:~charmers/charms/precise/mysql/trunk'}
        mysqlmock.provides = {'db': {'interface': 'mysql'}}
        mysqlmock.url = None

        mcharm.side_effect = [mysqlmock, wpmock]
        d = Deployment(juju_env='gojuju', sentries=False)
        d.add('mysql')
        d.configure('mysql', {'tuning': 'fastest'})
        d.add('wordpress')
        d.relate('mysql:db', 'wordpress:db')
        schema = {'gojuju': {
            'services': {
                'mysql': {
                    'branch': 'lp:~charmers/charms/precise/mysql/trunk',
                    'num_units': 1,
                    'options': {'tuning': 'fastest'},
                },
                'wordpress': {
                    'branch': 'lp:~charmers/charms/precise/wordpress/trunk',
                    'num_units': 1
                }
            },
            'series': 'precise',
            'relations': [['mysql:db', 'wordpress:db']],
        }}
        self.assertEqual(schema, d.schema())

    @patch.dict('os.environ', {'JUJU_TEST_CHARM': 'charmbook'})
    def test_juju_test_charm(self):
        d = Deployment(juju_env='gogo')
        self.assertEqual('charmbook', d.charm_name)

    def test_add_post_deploy(self):
        d = Deployment(juju_env='gogo')
        d.deployed = True
        self.assertRaises(NotImplementedError, d.add, 'mysql')

    def test_relate_before_service_deployed(self):
        d = Deployment(juju_env='gogo')
        d.deployed = True
        with self.assertRaises(ValueError) as e:
            d.relate('mysql:db', 'wordpress:db')
            self.assertEqual(
                'Can not relate, service not deployed yet', str(e))

    def test_unrelate_not_enough(self):
        d = Deployment(juju_env='gogo')
        self.assertRaises(LookupError, d.unrelate, 'mysql')

    def test_unrelate_too_many(self):
        d = Deployment(juju_env='gogo')
        self.assertRaises(LookupError, d.unrelate,
                          'mysql', 'wordpress', 'charm')

    def test_unrelate_bad_service_format(self):
        d = Deployment(juju_env='gogo')
        d.deployed = True
        with self.assertRaises(ValueError) as e:
            d.unrelate('mysql', 'wordpress')
            self.assertEqual(
                str(e), 'All relations must be explicit, service:relation')

    @patch('amulet.deployer.juju')
    def test_action_defined(self, mj):
        mj.return_value = '{"action": "description"}'
        d = Deployment(juju_env='gojuju')
        d.add('mysql')
        actions = d.action_defined('mysql')
        self.assertEquals(actions, {"action": "description"})
        mj.assert_has_calls([call(['action', 'defined', 'mysql', '--format', 'json'])])

    @patch('amulet.deployer.juju')
    def test_action_do(self, mj):
        mj.return_value = '{"Action queued with id": "some-action-id"}'
        d = Deployment(juju_env='gojuju')
        d.add('mysql')
        uuid = d.action_do('mysql/0', 'run')
        self.assertEquals(uuid, "some-action-id")
        mj.assert_has_calls([call(['action', 'do', 'mysql/0', 'run', '--format', 'json'])])

    @patch('amulet.deployer.juju')
    def test_action_fetch(self, mj):
        mj.side_effect = ['{"Action queued with id": "some-action-id"}',
                          '{"results":{"key":"value"},"status":"completed",'
                          '"timing":{"completed":"2015-07-21 09:05:11 +0300 EEST",'
                          '"enqueued":"2015-07-21 09:05:06 +0300 EEST",'
                          '"started":"2015-07-21 09:05:09 +0300 EEST"}}']
        d = Deployment(juju_env='gojuju')
        d.add('mysql')
        uuid = d.action_do('mysql/0', 'run', {"action_param": "action_value"})
        self.assertEquals(uuid, "some-action-id")
        results = d.action_fetch(uuid)
        self.assertEquals(results, {'key': 'value'})
        mj.assert_has_calls([call(['action', 'do', 'mysql/0', 'run', '--format', 'json', 'action_param=action_value']),
                            call(['action', 'fetch', 'some-action-id', '--format', 'json', '--wait', '600'])])

    @patch('amulet.deployer.juju')
    def test_action_fetch_nowait_fail(self, mj):
        mj.side_effect = ['{"Action queued with id": "some-action-id"}',
                          '{"status":"running",'
                          '"timing":{"enqueued":"2015-07-21 09:50:59 +0300 EEST",'
                          '"started":"2015-07-21 09:51:04 +0300 EEST"}}']
        d = Deployment(juju_env='gojuju')
        d.add('mysql')
        uuid = d.action_do('mysql/0', 'run')
        self.assertEquals(uuid, "some-action-id")
        results = d.action_fetch(uuid, timeout=None)
        self.assertEquals(results, {})
        mj.assert_has_calls([call(['action', 'do', 'mysql/0', 'run', '--format', 'json']),
                             call(['action', 'fetch', 'some-action-id', '--format', 'json'])])

    @patch('amulet.deployer.juju')
    def test_action_fetch_wait(self, mj):
        mj.side_effect = ['{"Action queued with id": "some-action-id"}',
                          '{"results":{"key":"value"},"status":"completed",'
                          '"timing":{"completed":"2015-07-21 09:05:11 +0300 EEST",'
                          '"enqueued":"2015-07-21 09:05:06 +0300 EEST",'
                          '"started":"2015-07-21 09:05:09 +0300 EEST"}}']
        d = Deployment(juju_env='gojuju')
        d.add('mysql')
        uuid = d.action_do('mysql/0', 'run')
        self.assertEquals(uuid, "some-action-id")
        results = d.action_fetch(uuid)
        self.assertEquals(results, {'key': 'value'})
        mj.assert_has_calls([call(['action', 'do', 'mysql/0', 'run', '--format', 'json']),
                             call(['action', 'fetch', 'some-action-id', '--format', 'json', '--wait', '600'])])

    @patch('amulet.deployer.juju')
    def test_unrelate(self, mj):
        d = Deployment(juju_env='gogo')
        d._relate('mysql:db', 'charm:db')
        d.deployed = True
        d.unrelate('mysql:db', 'charm:db')
        mj.assert_has_calls([
            call(['remove-relation',
                  'mysql:db', 'charm:db']),
            ])

    def test_unrelate_post_deploy(self):
        d = Deployment(juju_env='gogo')
        with self.assertRaises(ValueError) as e:
            d.unrelate('mysql:db', 'wordpress:db')
            self.assertEqual('Relation does not exist', str(e))

    @patch('amulet.deployer.juju')
    def test_remove_unit_m(self, mj):
        d = Deployment(juju_env='gogo')
        d.add('mysql', units=2)
        d.deployed = True
        d.remove_unit('mysql/1')
        mj.assert_called_with(['remove-unit', 'mysql/1'])

    def test_remove_unit_env_not_setup(self):
        d = Deployment(juju_env='gogo')
        d.add('mysql', units=2)
        self.assertRaises(NotImplementedError, d.remove_unit, 'mysql/0')

    def test_remove_unit_no_args(self):
        d = Deployment(juju_env='gogo')
        d.add('mysql', units=2)
        d.deployed = True
        self.assertRaises(ValueError, d.remove_unit)

    def test_remove_unit_not_a_unit(self):
        d = Deployment(juju_env='gogo')
        d.add('mysql', units=2)
        d.deployed = True
        self.assertRaises(ValueError, d.remove_unit, 'mysql/1', 'lolk')

    def test_remove_unit_not_deployed(self):
        d = Deployment(juju_env='gogo')
        d.add('mysql', units=2)
        d.deployed = True
        self.assertRaises(ValueError, d.remove_unit, 'wordpress/1')


class GetCharmNameTest(unittest.TestCase):
    def setUp(self):
        self.dir_ = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir_)

    def test_name_from_yaml(self):
        """Charm name pulled from metadata.yaml if it exists"""
        with open(os.path.join(self.dir_, 'metadata.yaml'), 'w') as f:
            f.write('name: testcharm')

        self.assertEqual(get_charm_name(self.dir_), 'testcharm')

    def test_name_from_dir(self):
        """Charm name equals dir name if no metadata.yaml exists"""
        self.assertEqual(
            get_charm_name(self.dir_), os.path.basename(self.dir_))
