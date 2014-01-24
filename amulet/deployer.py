
import os
import sys
import json
import copy
import shutil
import subprocess
import tempfile

from charmworldlib.charm import Charm

from . import helpers
from . import charmstore
from . import sentry

from . import wait
from .charm import Builder


_default_sentry_template = os.path.join(
    os.path.abspath(os.path.dirname(__file__)), 'charms/sentry')


class Deployment(object):
    def __init__(self, juju_env=None, series='precise', sentries=True,
                 juju_deployer='juju-deployer',
                 sentry_template=None):
        self.services = {}
        self.relations = []
        self.interfaces = []
        self.series = series
        self.deployed = False
        self.juju_env = juju_env or helpers.default_environment()
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

    def load(self, deploy_cfg):
        self.juju_env = list(deploy_cfg.keys())[0]
        schema = deploy_cfg[self.juju_env]
        self.services = schema['services']
        self.series = schema['series']
        self.relations = []

        for rel in schema['relations']:
            self.relations.append(rel)

    def add(self, service, charm=None, units=1):
        if service in self.services:
            raise ValueError('Service is already set to be deployed')
        if charm:
            if charm.startswith('lp:'):
                charm_branch = charm
                charm_name = None
            elif os.path.exists(charm):
                charm_branch = charm
                charm_name = os.path.basename(charm)
            else:
                charm = Charm(charm)
                charm_name = charm.name
                charm_branch = charm.code_source['location']
        else:
            charm_name = service
            charm = Charm(service)
            charm_branch = charm.code_source['location']

        if 'JUJU_TEST_CHARM' in os.environ:
            pass  # Copy the current parent directory to temp and deploy that
        elif self.charm_name:
            if charm_name == self.charm_name:
                charm_branch = os.getcwd()

        self.services[service] = {'branch': charm_branch}
        if units > 1:
            self.services[service]['num_units'] = units

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

    def configure(self, service, options):
        if service not in self.services:
            raise ValueError('Service has not yet been described')
        if not 'options' in self.services[service]:
            self.services[service]['options'] = options
        else:
            self.services[service]['options'].update(options)

    def expose(self, service):
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
            with helpers.timeout(timeout):
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
            self.sentry = sentry.Talisman(self.services)

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
                self.expose(sentry.metadata['name'])
                self._sentries[sentry.metadata['name']] = sentry
                self.services[service]['_has_sentry'] = True

        # Build relationship sentry
        if not self.relationship_sentry:
            # Auto generate name
            rel_sentry = Builder('relation-sentry', self.sentry_template)

            self.add(rel_sentry.metadata['name'], rel_sentry.charm)
            self.expose(rel_sentry.metadata['name'])
            self._sentries[rel_sentry.metadata['name']] = rel_sentry
            rel_sentry.write_metadata()
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

    def cleanup(self):
        shutil.rmtree(self.deployer_dir)
        for sentry in self._sentry:
            shutil.rmtree(os.path.dirname(self._sentry[sentry].charm))


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
