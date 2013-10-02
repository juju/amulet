
import os
import re
import yaml
import json
import copy
import urllib
import subprocess
import requests
import tempfile

from . import helpers
from . import charmstore
from . import waiter

from .charm import Builder

from collections import namedtuple


class Deployment(object):
    def __init__(self, juju_env=None, series='precise', sentries=True,
                 juju_deployer='juju-deployer',
                 sentry_template='/usr/share/amulet/charms/sentry'):
        self.services = {}
        self.relations = []
        self.interfaces = []
        self.series = series
        self.deployed = False
        self.juju_env = juju_env or helpers.default_environment()

        self.sentry = Talisman()
        self._sentries = {}
        self.use_sentries = sentries
        self.sentry_blacklist = []
        self.sentry_template = sentry_template
        self.relationship_sentry = None

        self.deployer = juju_deployer
        self.deployer_dir = tempfile.mkdtemp(prefix='amulet_deployment_')
        self.charm_cache = {}

    def load(self, deploy_cfg):
        self.juju_env = list(deploy_cfg.keys())[0]
        schema = deploy_cfg[self.juju_env]
        self.services = schema['services']
        self.series = schema['series']
        self.relations = []

        for rel in schema['relations']:
            self.relations.append(rel)

    def add(self, service, charm=None, units=1):
        # Do charm revision look ups?
        if service in self.services:
            raise ValueError('Service is already set to be deployed')
        if charm and charm.startswith('cs:~'):
            m = re.search('^cs:(~[\w-]+)/([\w-]+)', charm)
            charm = 'lp:%s/charms/%s/%s/trunk' % (m.group(1), self.series,
                                                  m.group(2))
            charm_name = m.group(2)
        #if charm and charm.startswith('lp:'):
        #

        self.services[service] = {'branch': charm or 'lp:charms/%s' % service}
        if units > 1:
            self.services[service]['units'] = units

    def relate(self, *args):
        if len(args) < 2:
            raise LookupError('Need at least two services:relation')

        for srv_rel in args:
            if not ':' in srv_rel:
                raise ValueError('All relations must be explicit, ' +
                                 'service:relation')

            service, relation = srv_rel.split(':')
            if service not in self.services:
                raise ValueError('Can not relate, service not deployed yet')
        args = list(args)
        first = args.pop(0)
        for srv in args:
            self.relations.append([first, srv])

    def schema(self):
        return self.deployer_map(self.services, self.relations)

    def configure(self, service, **options):
        if service not in self.services:
            raise ValueError('Service has not yet been described')
        if not 'options' in self.services[service]:
            self.services[service]['options'] = options
        else:
            self.services[service]['options'].update(options)

    def setup(self, timeout=600):
        if not self.deployer:
            raise NameError('Path to juju-deployer is not defined.')

        _, s = tempfile.mkstemp(prefix='amulet-juju-deployer-', suffix='.json')
        with open(s, 'w') as f:
            f.write(json.dumps(self.schema()))

        try:
            with helpers.timeout(timeout):
                subprocess.check_call([os.path.expanduser(self.deployer), '-W',
                                       '-c', s, '-e', self.juju_env,
                                       self.juju_env], cwd=self.deployer_dir)
            self.deployed = True
        except subprocess.CalledProcess:
            raise
        finally:
            os.remove(s)

        if not self.deployed:
            raise Exception('Deployment failed for an unknown reason')

        if self.deployed and self.use_sentries:
            status = waiter.status(self.juju_env)
            for service in self.services:
                if not service in status['services']:
                    continue  # Raise something?

                # self.sentry.service[service] = ServiceSentry()

                service_status = status['services'][service]

                if not 'units' in service_status:
                    continue  # It's a subordinate

                for unit in service_status['units']:
                    unit_data = service_status['units'][unit]
                    self.sentry.unit[unit] = UnitSentry.fromunitdata(unit_data)

    def deployer_map(self, services, relations):
        if self.use_sentries:
            self.build_sentries()

        deployer_map = {
            self.juju_env: {
                'series': self.series,
                'services': self.services,
                'relations': self.build_relations()
            }
        }

        return deployer_map

    def build_relations(self):
        relations = []
        for rel in self.relations:
            relations.append(rel)

        return relations

    def build_sentries(self):
        services = copy.deepcopy(self.services)
        for service, details in services.items():
            if service in self._sentries:
                continue

            if not '_has_sentry' in details or not details['_has_sentry']:
                sentry = Builder('%s-sentry' % service, self.sentry_template,
                                 subordinate=True)
                self.add(sentry.metadata['name'], sentry.charm)
                self.relate('%s:juju-info' % service, '%s:juju-info'
                            % sentry.metadata['name'])
                self._sentries[sentry.metadata['name']] = sentry
                self.services[service]['_has_sentry'] = True

        # Build relationship sentry
        if not self.relationship_sentry:
            # Auto generate name
            rel_sentry = Builder('relation-sentry', self.sentry_template)

            self.add(rel_sentry.metadata['name'], rel_sentry.charm)
            self._sentries[rel_sentry.metadata['name']] = rel_sentry
            self.relationship_sentry = rel_sentry

        relations = copy.deepcopy(self.relations)
        relation_sentry = self.relationship_sentry.metadata['name']
        for relation in relations:
            for rel in relation:
                service, rel_name = rel.split(':')
                if service in self._sentries:
                    break
            else:
                relation_name = "-".join(relation).replace(':', '_')
                self.relations.remove(relation)
                try:
                    interface = charmstore.get_relation(service, rel_name)[1]
                except:
                    continue

                self.relationship_sentry.provide('%s-%s' %
                                                 ('requires', relation_name),
                                                 interface)
                self.relationship_sentry.require('%s-%s' %
                                                 ('provides', relation_name),
                                                 interface)

                for rel in relation:
                    rel_data = charmstore.get_relation(*rel.split(':'))
                    self.relate('%s:%s-%s'
                                % (relation_sentry, rel_data[0],
                                   relation_name), rel)


class SentryError(Exception):
    pass


class Sentry(object):
    def __init__(self, address, port=9001):
        self.config = {}
        self.config['address'] = 'https://%s:%s' % (address, port)

    def file(self, filename):
        return self.file_stat(filename)

    def file_stat(self, filename):
        raise NotImplemented()

    def file_contents(self, filename):
        raise NotImplemented()

    def directory(self, *args):
        return self.directory_stat(*args)

    def directory_stat(self, *args):
        raise NotImplemented()

    def directory_contents(self, *args):
        return self.directory_listing(*args)

    def directory_listing(self, *args):
        raise NotImplemented()

    def juju_agent(self):
        return self._fetch('/juju').json()

    def _fetch(self, endpoint, query={}, data=None):
        url = "%s/%s?%s" % (self.config['address'], endpoint,
                            urllib.parse.urlencode(query))
        if data:
            return requests.post(url, data=data, verify=False)
        else:
            return requests.get(url, verify=False)


class UnitSentry(Sentry):
    @classmethod
    def fromunit(cls, unit):
        pass

    @classmethod
    def fromunitdata(cls, unit_data):
        address = unit_data['public-address']
        unitsentry = cls(address)
        unitsentry.info = unit_data
        return unitsentry

    def file_stat(self, filename):
        r = self._fetch_filesystem('/file', {'name': filename})
        return r.json()

    def _fetch_filesystem(self, endpoint, params):
        r = self._fetch(endpoint, params)
        if r.status_code == 404:
            raise IOError('%s does not exist on unit' % params['name'])
        elif r.status_code != 200:
            raise SentryError('API returned the following: %s' % r.status_code)

        return r

    def file_contents(self, filename):
        r = self._fetch_filesystem('/file/contents', {'name': filename})
        return r.text

    def directory_stat(self, path):
        r = self._fetch_filesystem('/directory', {'name': path})
        return r.json()

    def directory_listing(self, path):
        r = self._fetch_filesystem('/directory/contents', {'name': path})
        return r.json()

    #d.sentry.unit[].relation('db', 'mysql:db')
    def relation(self, from_rel, to_rel):
        pass


# Possibly use to build out instead of having code in setup()?
class Talisman(object):
    def __init__(self):
        self.unit = {}
        self.service = {}
        self.relation = {}

    def wait(self, timeout=300):
        import time
        #for unit in self.unit:
        ready = False
        try:
            with helpers.timeout(timeout):
                # Make sure we're in a 'started' state across the board
                waiter.wait(timeout=timeout)
                while not ready:
                    for unit in self.unit.keys():
                        status = self.unit[unit].juju_agent()
                        # Check if we have a hook key and it's not None
                        if 'hook' in status and status['hook']:
                            ready = False
                            break
                        else:
                            ready = True
        except:
            raise

    def _sync(self):
        pass

class ServiceSentry(Sentry):
    pass


class RelationSentry(Sentry):
    pass


def setup_parser(parent):
    def default_options(parser):
        parser.add_argument('-d', '--deployment',
                            help='unique name for deployment')
        parser.add_argument('-e', '--environment', dest='juju_env',
                            help="Juju environment")

    def list_deployments():
        if 'AMULET_DEPLOYER' in os.environ:
            return dict([x.split(':') for x in
                         os.environ['AMULET_DEPLOYER'].split(';')])
        else:
            return {}

    def add_cmd(args):
        try:
            wait(*args.services, **vars(args))
        except TimeoutError:
            sys.stderr.write('Timeout criteria was met\n')
            sys.exit(124)
        except:
            sys.stderr.write('Unexpected error occurred\n')
            raise

        sys.exit(0)

    def relate_cmd(args):
        pass

    parser = parent.add_parser('deployer', help='build deployer schema')
    deployer_subs = parser.add_subparsers()
    add = deployer_subs.add_parser('add',
                                   help='Add SERVICE to deployment')

    default_options(add)
    add.add_argument('-n', '--num-units', help='number of units to deploy',
                     default=1, type=int)
    add.add_argument('charm', nargs='?', help='charm to deploy')
    add.add_argument('service', nargs='?', help='service name', default=None)
    add.set_defaults(func=add_cmd)

    relate = deployer_subs.add_parser('relate',
                                      help='Relate two services to each other')

    default_options(relate)
    relate.add_argument('services', nargs=2, help='service:relation')
    relate.set_defaults(func=relate_cmd)
