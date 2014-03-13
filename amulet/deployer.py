
import os
import json
import copy
import base64
import shutil
import subprocess
import tempfile

from .helpers import default_environment, juju, timeout as unit_timesout
from .sentry import Talisman

from .charm import Builder, get_relation, get_charm

_default_sentry_template = os.path.join(
    os.path.abspath(os.path.dirname(__file__)), 'charms/sentry')


class Deployment(object):
    def __init__(self, juju_env=None, series='precise', sentries=True,
                 juju_deployer='juju-deployer',
                 sentry_template=None):
        self.services = {}
        self.relations = []
        self.interfaces = []
        self.subordinates = []
        self.series = series
        self.deployed = False
        self.juju_env = juju_env or default_environment()
        self.charm_name = os.path.basename(os.getcwd())

        self.sentry = None
        self._sentries = {}
        self.use_sentries = sentries
        self.sentry_blacklist = []
        self.sentry_template = sentry_template or _default_sentry_template
        self.relationship_sentry = None

        self.deployer = juju_deployer
        self.deployer_dir = tempfile.mkdtemp(prefix='amulet_deployment_')
        self.charm_cache = {}

        if 'JUJU_TEST_CHARM' in os.environ:
            self.charm_name = os.environ['JUJU_TEST_CHARM']

    def load(self, deploy_cfg):
        self.juju_env = list(deploy_cfg.keys())[0]
        schema = deploy_cfg[self.juju_env]
        self.services = schema['services']
        self.series = schema['series']
        self.relations = []

        for rel in schema['relations']:
            self.relations.append(rel)

    def add(self, service, charm=None, units=1):
        if self.deployed:
            raise NotImplementedError('Environment already setup')
        subordinate = False
        if service in self.services:
            raise ValueError('Service is already set to be deployed')
        if charm:
            c = get_charm(charm)
        else:
            if service == self.charm_name:
                c = get_charm(os.getcwd())
            else:
                c = get_charm(service)

        if c.subordinate:
            subordinate = True
            for rtype in ['provides', 'requires']:
                try:
                    rels = getattr(c, rtype)
                    for relation in rels:
                        rel = rels[relation]
                        if 'scope' in rel and rel['scope'] == 'container':
                            self.subordinates.append('%s:%s' %
                                                     (service, relation))
                except:
                    pass

        if c.url:
            self.services[service] = {'charm': c.url}
        else:
            self.services[service] = {'branch': c.code_source['location']}
        if subordinate:
            self.services[service]['_has_sentry'] = True
        if units > 1:
            self.services[service]['num_units'] = units

        self.charm_cache[service] = c

    def relate(self, *args):
        if len(args) < 2:
            raise LookupError('Need at least two services:relation')
        if self.deployed:
            raise NotImplementedError('Environment already setup')

        for srv_rel in args:
            if not ':' in srv_rel:
                raise ValueError('All relations must be explicit, ' +
                                 'service:relation')

            srv, rel = srv_rel.split(':')
            if srv not in self.services:
                raise ValueError('Can not relate, service not deployed yet')

            c = self.charm_cache[srv]
            if rel not in list(c.provides.keys()) + list(c.requires.keys()) \
                    + ['juju-info']:
                raise ValueError('%s does not exist for %s' % (rel, srv))

        args = list(args)
        first = args.pop(0)
        for srv in args:
            self._relate(first, srv)

    def _relate(self, a, b):
        self.relations.append([a, b])

    def unrelate(self, *args):
        if len(args) < 2:
            raise LookupError('Need at least two services:relation')
        if not self.deployed:
            raise NotImplementedError('Environment not setup yet')

        return juju(['remove-relation'] + [r for r in args])

    def schema(self):
        return self.deployer_map(self.services, self.relations)

    def configure(self, service, options):
        for k, v in options.items():
            include_token = 'include-base64://'
            if type(v) is str and v.startswith(include_token):
                v = v.replace(include_token, '')
                with open(os.path.join(os.getcwd(), 'tests', v)) as f:
                    v = base64.b64encode(f.read())
                service['options'][k] = v

        if self.deployed:
            opts = ['set', service]
            for k, v in options.items():
                opts.append("%s='%s'" % (k, v))
            return juju(opts)

        if service not in self.services:
            raise ValueError('Service has not yet been described')
        if not 'options' in self.services[service]:
            self.services[service]['options'] = options
        else:
            self.services[service]['options'].update(options)

    def expose(self, service):
        if self.deployed:
            return juju(['expose', service])

        if service not in self.services:
            raise ValueError('%s has not yet been described' % service)
        self.services[service]['expose'] = True

    def setup(self, timeout=600):
        if not self.deployer:
            raise NameError('Path to juju-deployer is not defined.')

        _, s = tempfile.mkstemp(prefix='amulet-juju-deployer-', suffix='.json')
        with open(s, 'w') as f:
            f.write(json.dumps(self.schema()))

        try:
            with unit_timesout(timeout):
                subprocess.check_call([os.path.expanduser(self.deployer), '-W',
                                       '-c', s, '-e', self.juju_env,
                                       self.juju_env], cwd=self.deployer_dir)
            self.deployed = True
        except subprocess.CalledProcessError:
            raise
        finally:
            os.remove(s)

        if not self.deployed:
            raise Exception('Deployment failed for an unknown reason')

        if self.deployed and self.use_sentries:
            self.sentry = Talisman(self.services)

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
                self._relate('%s:juju-info' % service,
                             '%s:juju-info' % sentry.metadata['name'])
                self.expose(sentry.metadata['name'])
                self._sentries[sentry.metadata['name']] = sentry
                self.services[service]['_has_sentry'] = True

        # Build relationship sentry
        if not self.relationship_sentry:
            # Auto generate name
            rel_sentry = Builder('relation-sentry', self.sentry_template)
            rel_sentry.write_metadata()

            self.add(rel_sentry.metadata['name'], rel_sentry.charm)
            self.expose(rel_sentry.metadata['name'])
            self._sentries[rel_sentry.metadata['name']] = rel_sentry
            rel_sentry.write_metadata()
            self.relationship_sentry = rel_sentry

        relations = copy.deepcopy(self.relations)
        relation_sentry = self.relationship_sentry.metadata['name']
        for relation in relations:
            for rel in relation:
                if rel in self.subordinates:
                    break
                service, rel_name = rel.split(':')
                if service in self._sentries:
                    break
            else:
                relation_name = "-".join(relation).replace(':', '_')
                self.relations.remove(relation)
                try:
                    interface = get_relation(service, rel_name)[1]
                except:
                    continue

                if not interface:
                    raise Exception('Unable to detect interface for %s on %s'
                                    % (service, rel_name))

                self.relationship_sentry.provide('%s-%s' %
                                                 ('requires', relation_name),
                                                 interface)
                self.relationship_sentry.require('%s-%s' %
                                                 ('provides', relation_name),
                                                 interface)

                for rel in relation:
                    rel_data = get_relation(*rel.split(':'))
                    self._relate('%s:%s-%s'
                                 % (relation_sentry, rel_data[0],
                                    relation_name), rel)

    def cleanup(self):
        shutil.rmtree(self.deployer_dir)
        for sentry in self._sentries:
            shutil.rmtree(os.path.dirname(self._sentries[sentry].charm))
