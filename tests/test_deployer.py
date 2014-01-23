"""Unit test for amulet.wait"""

import os
import unittest
import json

from amulet import Deployment
from mock import patch, MagicMock

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

    def test_load(self):
        d = Deployment(juju_env='gojuju')
        schema = '{"gojuju": {"series": "raring", "services": {"wordpress": \
                  {"branch": "lp:~charmers/charms/precise/wordpress/trunk"}, \
                  "mysql": {"options": {"tuning": "fastest"}, \
                  "branch": "lp:~charmers/charms/precise/mysql/trunk"}}, \
                  "relations": [["mysql:db", "wordpress:db"]]}}'
        dmap = json.loads(schema)
        d.load(dmap)
        self.assertEqual(dmap['gojuju']['services'], d.services)
        self.assertEqual(dmap['gojuju']['relations'], d.relations)
        self.assertEqual(dmap['gojuju']['series'], d.series)

    @patch('amulet.deployer.Charm')
    def test_add(self, mcharm):
        charm = mcharm.return_value
        charm.code_source = {'location':
                             'lp:~charmers/charms/precise/charm/trunk'}
        d = Deployment(juju_env='gojuju')
        d.add('charm')
        self.assertEqual({'charm': {'branch':
                                    'lp:~charmers/charms/precise/charm/trunk'}
                          }, d.services)

    @patch('amulet.deployer.Charm')
    def test_add_branch(self, mcharm):
        charm = mcharm.return_value
        charm.code_source = {'location': 'lp:~foo/charms/precise/baz/trunk'}
        d = Deployment(juju_env='gojuju')
        d.add('bar', 'cs:~foo/baz')
        self.assertEqual({'bar':
                         {'branch': 'lp:~foo/charms/precise/baz/trunk'}},
                         d.services)

    @patch('amulet.deployer.Charm')
    def test_add_units(self, mcharm):
        charm = mcharm.return_value
        charm.code_source = {'location': 'lp:charms/charm'}
        d = Deployment(juju_env='gojuju')
        d.add('charm', units=2)
        self.assertEqual({'charm': {'branch': 'lp:charms/charm',
                                    'num_units': 2}}, d.services)

    @patch('amulet.deployer.Charm')
    def test_add_error(self, mcharm):
        d = Deployment(juju_env='gojuju')
        d.add('bar')
        self.assertRaises(ValueError, d.add, 'bar')

    @patch('amulet.deployer.Charm')
    def test_relate(self, mcharm):
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

    @patch('amulet.deployer.Charm')
    def test_relate_not_deployed(self, mcharm):
        d = Deployment(juju_env='gojuju')
        d.add('foo')
        self.assertRaises(ValueError, d.relate, 'foo:f', 'bar:a')

    @patch('amulet.deployer.Charm')
    def test_configure(self, mcharm):
        charm = mcharm.return_value
        charm.code_source = {'location':
                             'lp:~charmers/charms/precise/wordpress/trunk'}
        d = Deployment(juju_env='gojuju')
        d.add('wordpress')
        d.configure('wordpress', {'tuning': 'optimized'})
        d.configure('wordpress', {'wp-content': 'f', 'port': 100})
        self.assertEqual({'wordpress':
                          {'branch':
                           'lp:~charmers/charms/precise/wordpress/trunk',
                           'options': {'tuning': 'optimized',
                                       'wp-content': 'f',
                                       'port': 100}}}, d.services)

    def test_configure_not_deployed(self):
        d = Deployment(juju_env='gojuju')
        self.assertRaises(ValueError, d.configure, 'wordpress',
                          {'tuning': 'optimized'})

    @patch('amulet.deployer.Charm')
    def test_expose(self, mcharm):
        charm = mcharm.return_value
        charm.code_source = {'location':
                             'lp:~charmers/charms/precise/wordpress/trunk'}
        d = Deployment(juju_env='gojuju')
        d.add('wordpress')
        d.expose('wordpress')
        self.assertEqual({'wordpress':
                          {'branch':
                           'lp:~charmers/charms/precise/wordpress/trunk',
                           'expose': True}}, d.services)

    def test_expose_not_deployed(self):
        d = Deployment(juju_env='gojuju')
        self.assertRaises(ValueError, d.expose, 'wordpress')

    @patch('amulet.deployer.Charm')
    def test_schema(self, mcharm):
        wpmock = MagicMock()
        mysqlmock = MagicMock()
        wpmock.code_source = {'location':
                              'lp:~charmers/charms/precise/wordpress/trunk'}
        mysqlmock.code_source = {'location':
                                 'lp:~charmers/charms/precise/mysql/trunk'}
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

    def test_build_sentries_writes_relationship_sentry_metadata(self):
        """Even if there are no relations the metadata.yaml is written."""
        d = Deployment(juju_env='gojuju', sentries=True)

        d.build_sentries()

        self.assertIn('metadata.yaml',
                      os.listdir(d.relationship_sentry.charm))
