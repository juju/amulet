
import os
import re
import yaml
import json
import subprocess
import tempfile

import helpers


class Deployer(object):
    def __init__(self, environment=None, series='precise', sentries=True,
                 juju_deployer=None):
        self.services = {}
        self.relations = {}
        self.series = series
        self.sentries = sentries
        self.environment = environment or helpers.default_environment()
        self.interfaces = []
        self.deployer = juju_deployer

    def load(self, deploy_cfg):
        self.environment = deploy_cfg.keys()[0]
        schema = deploy_cfg[self.environment]
        self.services = schema['services']
        self.series = schema['series']

        for rel in schema['relations']:
            self.relations[rel] = schema['relations'][rel]['consumes']

    def add(self, service, charm=None, units=1):
        # Do charm revision look ups?
        if service in self.services:
            raise ValueError('Service is already set to be deployed')
        if charm and charm.startswith('cs:~'):
            m = re.search('^cs:(~[\w-]+)/([\w-]+)', charm)
            charm = 'lp:%s/charms/%s/%s/trunk' % (m.group(1), self.series,
                                                  m.group(2))

        self.services[service] = {'branch': charm or 'lp:charms/%s' % service,
                                  'units': units}

    def relate(self, from_charm, to_charm):
        if not from_charm in self.relations:
            self.relations[from_charm] = []

        self.relations[from_charm].append(to_charm)

    def schema(self):
        return self.deployer_map(self.services, self.relations)

    def configure(self, service, **options):
        if service not in self.services:
            raise ValueError('Service has not yet been described')
        if not 'options' in self.services[service]:
            self.services[service]['options'] = options
        else:
            self.services[service]['options'].update(options)

    def setup(self, timeout=300):
        if not self.deployer:
            raise NameError('Path to juju-deployer is not defined.')

        _, s = tempfile.mkstemp(prefix='amulet-juju-deployer-', suffix='.json')
        with open(s, 'w') as f:
            f.write(json.dumps(self.schema()))

        try:
            with helpers.timeout(timeout):
                subprocess.check_call([os.path.expanduser(self.deployer), '-w',
                                       '-t', '-c', s, '-e', self.environment,
                                       '-L'])
        finally:
            os.remove(s)

    def deployer_map(self, services, relations):
        self.build_sentries(self.relations)
        deployer_map = {
            self.environment: {
                'series': self.series,
                'services': self.services,
                'relations': self.build_relations(self.relations)
            }
        }

        return deployer_map

    def _find_common_interface(self, *args):
        pass

    def build_relations(self, relation_data=None):
        if not relation_data:
            relation_data = self.relations

        weight = 100
        relations = {}
        for key in relation_data:
            relations[key] = {'weight': weight, 'consumes': relation_data[key]}
            weight -= 1

        return relations

    def build_sentries(self, relation_data=None):
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
            print >> sys.stderr, 'Timeout criteria was met'
            sys.exit(124)
        except:
            print >> sys.stderr, 'Unexpected error occurred'
            raise

        sys.exit(0)

    def relate_cmd(args):
        pass

    parser = parent.add_parser('deployer', help="build deployer schema")
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
