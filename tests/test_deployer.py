"""Unit test for amulet.wait"""

import os
import unittest
import json
import yaml

from amulet import Deployment
from amulet.deployer import CharmCache
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
        self.assertEqual(True, d.use_sentries)
        self.assertEqual({}, d._sentries)
        self.assertEqual([], d.relations)
        d.cleanup()

    def test_load(self):
        d = Deployment(juju_env='gojuju')
        schema = '{"mybundle": {"series": "raring", "services": {"wordpress": \
                  {"branch": "lp:~charmers/charms/precise/wordpress/trunk"}, \
                  "mysql": {"options": {"tuning": "fastest"}, \
                  "branch": "lp:~charmers/charms/precise/mysql/trunk"}}, \
                  "relations": [["mysql:db", "wordpress:db"]]}}'
        dmap = json.loads(schema)
        with patch.object(d, 'add') as add:
            with patch.object(d, 'configure') as configure:
                d.load(dmap)
        self.assertEqual(d.juju_env, 'gojuju')
        self.assertEqual(dmap['mybundle']['relations'], d.relations)
        self.assertEqual(dmap['mybundle']['series'], d.series)
        add.assert_has_calls([
            call('wordpress', charm=None, units=1),
            call('mysql', charm=None, units=1)],
            any_order=True
        )
        configure.assert_has_calls([
            call('mysql', {'tuning': 'fastest'}),
        ])
        d.cleanup()

    @patch('amulet.deployer.get_charm')
    def test_add(self, mcharm):
        charm = mcharm.return_value
        charm.subordinate = False
        charm.code_source = {'location':
                             'lp:~charmers/charms/precise/charm/trunk'}
        charm.url = 'cs:precise/charm'

        d = Deployment(juju_env='gojuju')
        d.add('charm')
        self.assertEqual({'charm': {'charm': 'cs:precise/charm'}}, d.services)
        d.cleanup()

    @patch('amulet.deployer.get_charm')
    def test_add_branch(self, mcharm):
        charm = mcharm.return_value
        charm.subordinate = False
        charm.code_source = {'location': 'lp:~foo/charms/precise/baz/trunk'}
        charm.url = None

        d = Deployment(juju_env='gojuju')
        d.add('bar', 'cs:~foo/baz')
        self.assertEqual({'bar':
                          {'branch': 'lp:~foo/charms/precise/baz/trunk'}},
                         d.services)
        d.cleanup()

    @patch('amulet.deployer.get_charm')
    def test_add_units(self, mcharm):
        charm = mcharm.return_value
        charm.subordinate = False
        charm.code_source = {'location': 'lp:charms/charm'}
        charm.url = None

        d = Deployment(juju_env='gojuju')
        d.add('charm', units=2)
        self.assertEqual({'charm': {'branch': 'lp:charms/charm',
                                    'num_units': 2}}, d.services)
        d.cleanup()

    @patch('amulet.deployer.get_charm')
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
        d.cleanup()

    def _make_mock_status(self, d):
        def _mock_status(juju_env):
            status = dict(services={})
            total_units = 1
            for service in d.services:
                status['services'][service] = dict(units={})
                for unit in range(d.services[service].get('num_units', 1)):
                    total_units += 1
                    status['services'][service]['units'][
                        '{}/{}'.format(service, unit)] = {
                        'public-address': '10.0.3.{}'.format(total_units)}
            status['services']['relation-sentry'] = {
                'units': {
                    'relation-sentry/0': {
                        'public-address': '10.0.3.1'}}}
            return status
        return _mock_status

    @patch('amulet.helpers.environments')
    @patch('amulet.sentry.waiter.status')
    @patch('amulet.deployer.subprocess')
    @patch('amulet.deployer.get_charm')
    def test_add_unit(self, mcharm, subprocess, waiter_status, environments):
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
        with patch('amulet.deployer.juju'):
            d.add_unit('charm')
        self.assertTrue('charm/1' in d.sentry.unit)

        d.cleanup()

    @patch('amulet.helpers.environments')
    @patch('amulet.sentry.waiter.status')
    @patch('amulet.deployer.subprocess')
    @patch('amulet.deployer.get_charm')
    def test_add_unit_error(self, mcharm, subprocess, waiter_status, environments):
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
        d.cleanup()

    @patch('amulet.deployer.get_charm')
    def test_add_error(self, mcharm):
        d = Deployment(juju_env='gojuju')
        d.add('bar')
        self.assertRaises(ValueError, d.add, 'bar')
        d.cleanup()

    @patch('amulet.deployer.get_charm')
    def test_relate(self, mcharm):
        a = mcharm.return_value
        a.provides = {'f': {'interface': 'test'}}
        a.requires = {'b': {'interface': 'test'}}

        d = Deployment(juju_env='gojuju')
        d.add('bar')
        d.add('foo')
        d.relate('foo:f', 'bar:b')
        self.assertEqual(d.relations, [['foo:f', 'bar:b']])
        d.cleanup()

    def test_relate_too_few(self):
        d = Deployment(juju_env='gojuju')
        self.assertRaises(LookupError, d.relate, 'foo:f')
        d.cleanup()

    def test_relate_no_relation(self):
        d = Deployment(juju_env='gojuju')
        self.assertRaises(ValueError, d.relate, 'foo', 'bar:a')
        d.cleanup()

    @patch('amulet.deployer.get_charm')
    def test_relate_relation_nonexist(self, mcharm):
        d = Deployment(juju_env='gojuju')
        d.add('bar')
        d.add('foo')

        self.assertRaises(ValueError, d.relate, 'foo:f', 'bar:b')
        d.cleanup()

    def test_relate_not_deployed(self):
        d = Deployment(juju_env='gojuju')
        self.assertRaises(ValueError, d.relate, 'foo:f', 'bar:a')
        d.cleanup()

    @patch('amulet.deployer.get_charm')
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
                           'options': {'tuning': 'optimized',
                                       'wp-content': 'f',
                                       'port': 100}}}, d.services)
        d.cleanup()

    def test_configure_not_deployed(self):
        d = Deployment(juju_env='gojuju')
        self.assertRaises(ValueError, d.configure, 'wordpress',
                          {'tuning': 'optimized'})
        d.cleanup()

    @patch('amulet.deployer.get_charm')
    def test_expose(self, mcharm):
        charm = mcharm.return_value
        charm.subordinate = False
        charm.code_source = {'location':
                             'lp:~charmers/charms/precise/wordpress/trunk'}
        charm.url = None

        d = Deployment(juju_env='gojuju')
        d.add('wordpress')
        d.expose('wordpress')
        self.assertEqual({'wordpress':
                          {'branch':
                           'lp:~charmers/charms/precise/wordpress/trunk',
                           'expose': True}}, d.services)
        d.cleanup()

    def test_expose_not_deployed(self):
        d = Deployment(juju_env='gojuju')
        self.assertRaises(ValueError, d.expose, 'wordpress')
        d.cleanup()

    @patch('amulet.deployer.get_charm')
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
        schema = {'gojuju': {'services': {'mysql': {
            'branch': 'lp:~charmers/charms/precise/mysql/trunk',
            'options': {'tuning': 'fastest'}},
            'wordpress': {'branch':
                          'lp:~charmers/charms/precise/wordpress/trunk'}},
            'series': 'precise', 'relations': [['mysql:db', 'wordpress:db']]}}
        self.assertEqual(schema, d.schema())
        d.cleanup()

    def test_build_sentries_writes_relationship_sentry_metadata(self):
        """Even if there are no relations the metadata.yaml is written."""
        d = Deployment(juju_env='gojuju', sentries=True)
        d.build_sentries()
        self.assertIn('metadata.yaml',
                      os.listdir(d.relationship_sentry.charm))
        d.cleanup()

    @patch.dict('os.environ', {'JUJU_TEST_CHARM': 'charmbook'})
    def test_juju_test_charm(self):
        d = Deployment(juju_env='gogo')
        self.assertEqual('charmbook', d.charm_name)
        d.cleanup()

    def test_add_post_deploy(self):
        d = Deployment(juju_env='gogo')
        d.deployed = True
        self.assertRaises(NotImplementedError, d.add, 'mysql')
        d.cleanup()

    def test_relate_post_deploy(self):
        d = Deployment(juju_env='gogo')
        d.deployed = True
        self.assertRaises(NotImplementedError, d.relate, 'mysql:db',
                          'wordpress:db')
        d.cleanup()

    def test_unrelate_not_enough(self):
        d = Deployment(juju_env='gogo')
        self.assertRaises(LookupError, d.unrelate, 'mysql')
        d.cleanup()

    def test_unrelate_too_many(self):
        d = Deployment(juju_env='gogo')
        self.assertRaises(LookupError, d.unrelate,
                          'mysql', 'wordpress', 'charm')
        d.cleanup()

    def test_unrelate_bad_service_format(self):
        d = Deployment(juju_env='gogo')
        d.deployed = True
        with self.assertRaises(ValueError) as e:
            d.unrelate('mysql', 'wordpress')
            self.assertEqual(
                str(e), 'All relations must be explicit, service:relation')
        d.cleanup()

    @patch.object(Deployment, '_get_sentry_relations')
    @patch('amulet.deployer.juju')
    def test_unrelate(self, mj, _get_sentry_relations):
        _get_sentry_relations.return_value = [
            ['relation-sentry:provides-mysql_db-charm_db', 'mysql:db'],
            ['relation-sentry:requires-mysql_db-charm_db', 'charm:db'],
        ]

        d = Deployment(juju_env='gogo')
        d.deployed = True
        d.unrelate('mysql:db', 'charm:db')
        mj.assert_has_calls([
            call(['remove-relation',
                  'relation-sentry:provides-mysql_db-charm_db', 'mysql:db']),
            call(['remove-relation',
                  'relation-sentry:requires-mysql_db-charm_db', 'charm:db']),
            ])
        d.cleanup()

    def test_unrelate_post_deploy(self):
        d = Deployment(juju_env='gogo')
        self.assertRaises(NotImplementedError, d.unrelate, 'mysql:db',
                          'wordpress:db')
        d.cleanup()

    def test_get_sentry_relations(self):
        d = Deployment(juju_env='gogo')
        d.relations = [
            ['relation-sentry:provides-mysql_db-charm_db', 'mysql:db'],
            ['relation-sentry:requires-mysql_db-charm_db', 'charm:db'],
        ]
        self.assertEqual(
            d._get_sentry_relations('charm:db', 'mysql:db'),
            d.relations)
        self.assertEqual(
            d._get_sentry_relations('mysql:db', 'charm:db'),
            list(reversed(d.relations)))
        d.cleanup()

    def test_get_sentry_relations_not_found(self):
        d = Deployment(juju_env='gogo')
        d.relations = []
        with self.assertRaises(LookupError) as e:
            d._get_sentry_relations('charm:db', 'mysql:db')
            self.assertEqual(
                str(e),
                'Could not find relation between charm:db and mysql:db')
        d.cleanup()

    @patch('amulet.deployer.juju')
    def test_remove_unit(self, mj):
        d = Deployment(juju_env='gogo')
        d.add('mysql', units=2)
        d.deployed = True
        d.remove_unit('mysql/1')
        mj.assert_called_with(['remove-unit', 'mysql/1'])
        d.cleanup()

    def test_remove_unit_env_not_setup(self):
        d = Deployment(juju_env='gogo')
        d.add('mysql', units=2)
        self.assertRaises(NotImplementedError, d.remove_unit, 'mysql/0')
        d.cleanup()

    def test_remove_unit_no_args(self):
        d = Deployment(juju_env='gogo')
        d.add('mysql', units=2)
        d.deployed = True
        self.assertRaises(ValueError, d.remove_unit)
        d.cleanup()

    def test_remove_unit_not_a_unit(self):
        d = Deployment(juju_env='gogo')
        d.add('mysql', units=2)
        d.deployed = True
        self.assertRaises(ValueError, d.remove_unit, 'mysql/1', 'lolk')
        d.cleanup()

    def test_remove_unit_not_deployed(self):
        d = Deployment(juju_env='gogo')
        d.add('mysql', units=2)
        d.deployed = True
        self.assertRaises(ValueError, d.remove_unit, 'wordpress/1')
        d.cleanup()

    def test_setup(self):
        pass


class CharmCacheTest(unittest.TestCase):
    def test_init(self):
        c = CharmCache('mytestcharm')
        self.assertEqual(c.test_charm, 'mytestcharm')

    @patch('amulet.deployer.get_charm')
    def test_getitem_service(self, get_charm):
        c = CharmCache('mytestcharm')
        charm = c['myservice']
        self.assertEqual(charm, get_charm.return_value)
        get_charm.assert_called_once_with('myservice')

        get_charm.reset_mock()
        charm2 = c['myservice']
        self.assertEqual(charm, charm2)
        self.assertFalse(get_charm.called)

    @patch('amulet.deployer.get_charm')
    def test_getitem_testcharm(self, get_charm):
        c = CharmCache('mytestcharm')
        charm = c['mytestcharm']
        self.assertEqual(charm, get_charm.return_value)
        get_charm.assert_called_once_with(os.getcwd())

    @patch('amulet.deployer.get_charm')
    def test_fetch_service(self, get_charm):
        c = CharmCache('mytestcharm')
        charm = c.fetch('myservice')
        self.assertEqual(charm, get_charm.return_value)
        get_charm.assert_called_once_with('myservice')

        get_charm.reset_mock()
        charm2 = c['myservice']
        self.assertEqual(charm, charm2)
        self.assertFalse(get_charm.called)

    @patch('amulet.deployer.get_charm')
    def test_fetch_charm(self, get_charm):
        c = CharmCache('mytestcharm')
        charm = c.fetch('myservice', 'anothercharm')
        self.assertEqual(charm, get_charm.return_value)
        get_charm.assert_called_once_with('anothercharm')

    @patch('amulet.deployer.get_charm')
    def test_fetch_testcharm(self, get_charm):
        c = CharmCache('mytestcharm')
        charm = c.fetch('myservice', 'mytestcharm')
        self.assertEqual(charm, get_charm.return_value)
        get_charm.assert_called_once_with(os.getcwd())
