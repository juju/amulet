"""Unit test for amulet.wait"""

import os
import unittest
import yaml
import json

from amulet import Deployment

from mock import patch, call, Mock, MagicMock

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
                  {"branch": "lp:charms/wordpress"}, "mysql": {"options": \
                  {"tuning": "fastest"}, "branch": "lp:charms/mysql"}}, \
                  "relations": [["mysql:db", "wordpress:db"]]}}'
        dmap = json.loads(schema)
        d.load(dmap)
        self.assertEqual(dmap['gojuju']['services'], d.services)
        self.assertEqual(dmap['gojuju']['relations'], d.relations)
        self.assertEqual(dmap['gojuju']['series'], d.series)

    def test_add(self):
        d = Deployment(juju_env='gojuju')
        d.add('charm')
        self.assertEqual({'charm': {'branch': 'lp:charms/charm'}}, d.services)

    def test_add_branch(self):
        d = Deployment(juju_env='gojuju')
        d.add('bar', 'cs:~foo/bar')
        self.assertEqual({'bar':
                         {'branch': 'lp:~foo/charms/precise/bar/trunk'}},
                         d.services)

    def test_add_units(self):
        d = Deployment(juju_env='gojuju')
        d.add('charm', units=2)
        self.assertEqual({'charm': {'branch': 'lp:charms/charm', 'units': 2}},
                         d.services)

    def test_add_error(self):
        d = Deployment(juju_env='gojuju')
        d.add('bar')
        self.assertRaises(ValueError, d.add, 'bar')

    def test_relate(self):
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

    def test_relate_not_deployed(self):
        d = Deployment(juju_env='gojuju')
        d.add('foo')
        self.assertRaises(ValueError, d.relate, 'foo:f', 'bar:a')

    def test_configure(self):
        d = Deployment(juju_env='gojuju')
        d.add('wordpress')
        d.configure('wordpress', tuning='optimized')
        d.configure('wordpress', **{'wp-content': 'f', 'port': 100})
        self.assertEqual({'wordpress': {'branch': 'lp:charms/wordpress',
                         'options': {'tuning': 'optimized', 'wp-content': 'f',
                          'port': 100}}}, d.services)

    def test_configure_not_deployed(self):
        d = Deployment(juju_env='gojuju')
        self.assertRaises(ValueError, d.configure, 'wordpress',
                          tuning='optimized')

    def test_schema(self):
        d = Deployment(juju_env='gojuju', sentries=False)
        d.add('mysql')
        d.configure('mysql', tuning='fastest')
        d.add('wordpress')
        d.relate('mysql:db', 'wordpress:db')
        schema = {'gojuju': {'services': {'mysql': {'branch':
                  'lp:charms/mysql', 'options': {'tuning': 'fastest'}},
                 'wordpress': {'branch': 'lp:charms/wordpress'}}, 'series':
                 'precise', 'relations': [['mysql:db', 'wordpress:db']]}}
        self.assertEqual(schema, d.schema())
