import os
import json
import base64
import shutil
import subprocess
import tempfile
import yaml

from .helpers import default_environment, juju, timeout as unit_timesout
from .sentry import Talisman

from .charm import get_charm


def get_charm_name(dir_):
    """Given a directory, return the name of the charm in that dir.

    If metadata.yaml exists in the dir, grab the charm name from there.
    Otherwise, return the name of the dir.

    """
    try:
        with open(os.path.join(dir_, 'metadata.yaml')) as f:
            return yaml.load(f)['name']
    except:
        return os.path.basename(dir_)


class CharmCache(dict):
    def __init__(self, test_charm):
        super(CharmCache, self).__init__()
        self.test_charm = test_charm

    def __getitem__(self, service):
        return self.fetch(service)

    def fetch(self, service, charm=None, series='precise'):
        try:
            return super(CharmCache, self).__getitem__(service)
        except KeyError:
            charm = charm or service
            self[service] = get_charm(
                os.getcwd() if charm == self.test_charm else charm,
                series=series,
            )
            return super(CharmCache, self).__getitem__(service)


class Deployment(object):
    def __init__(self, juju_env=None, series='precise',
                 juju_deployer='juju-deployer', **kw):
        self.services = {}
        self.relations = []
        self.interfaces = []
        self.subordinates = []
        self.series = series
        self.deployed = False
        self.juju_env = juju_env or default_environment()
        self.charm_name = get_charm_name(os.getcwd())

        self.sentry = None
        self.deployer = juju_deployer
        self.deployer_dir = tempfile.mkdtemp(prefix='amulet_deployment_')

        if 'JUJU_TEST_CHARM' in os.environ:
            self.charm_name = os.environ['JUJU_TEST_CHARM']

        self.charm_cache = CharmCache(self.charm_name)

    def load(self, deploy_cfg):
        schema = next(iter(deploy_cfg.values()))
        for service, service_config in schema['services'].items():
            constraints = service_config.get('constraints')
            if constraints:
                constraints = dict(
                    constraint.split('=')
                    for constraint in constraints.split()
                )
            self.add(
                service,
                charm=service_config.get('charm'),
                units=service_config.get('num_units', 1),
                constraints=constraints,
            )
            if service_config.get('options'):
                self.configure(service, service_config['options'])
        self.series = schema['series']
        self.relations = schema['relations']

    def add(self, service, charm=None, units=1, constraints=None):
        if self.deployed:
            raise NotImplementedError('Environment already setup')
        if service in self.services:
            raise ValueError('Service is already set to be deployed')

        c = self.charm_cache.fetch(service, charm, self.series)

        if c.subordinate:
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

        self.services[service]['num_units'] = units

        if constraints:
            if not isinstance(constraints, dict):
                raise ValueError('Constraints must be specified as a dict')

            r = []
            for k, v in constraints.items():
                r.append("%s=%s" % (k, v))

            self.services[service]['constraints'] = " ".join(r)

    def add_unit(self, service, units=1):
        if not isinstance(units, int) or units < 1:
            raise ValueError('Only positive integers can be used for units')
        if service not in self.services:
            raise ValueError('Service needs to be added before you can scale')

        self.services[service]['num_units'] = \
            self.services[service].get('num_units', 1) + units

        if self.deployed:
            juju(['add-unit', service, '-n', str(units)])
            self.sentry = Talisman(self.services)

    def remove_unit(self, *units):
        if not self.deployed:
            raise NotImplementedError('Environment not setup yet')
        if not units:
            raise ValueError('No units provided')
        for unit in units:
            if '/' not in unit:
                raise ValueError('%s is not a unit' % unit)
            service = unit.split('/')[0]
            if service not in self.services:
                raise ValueError('%s is not a deployed service' % service)

        juju(['remove-unit'] + list(units))

        for unit in units:
            if self.sentry and unit in self.sentry.unit:
                del self.sentry.unit[unit]
            service = unit.split('/')[0]
            self.services[service]['num_units'] = \
                min(0, self.services[service].get('num_units', 1) - 1)
    destroy_unit = remove_unit

    def remove_service(self, *services):
        if not services:
            raise ValueError('No services provided')
        for service in services:
            if service not in self.services:
                raise ValueError('%s is not a deployed service' % service)

        if self.deployed:
            juju(['remove-service'] + list(services))

        for service in services:
            self._remove_service_sentries(service)
            self._remove_service_relations(service)
            del self.services[service]
    destroy_service = remove_service

    def remove(self, *units_or_services):
        if not units_or_services:
            raise ValueError('No units or services provided')

        units_or_services = set(units_or_services)
        units = {s for s in units_or_services if '/' in s}
        services = units_or_services - units
        units = {u for u in units if u.split('/')[0] not in services}

        if units:
            self.remove_unit(*units)

        if services:
            self.remove_service(*services)
    destroy = remove

    def _remove_service_sentries(self, service):
        if not self.sentry:
            return

        for unit in list(self.sentry.unit):
            if unit.split('/')[0] == service:
                del self.sentry.unit[unit]

    def _remove_service_relations(self, service):
        for relation in self.relations[:]:
            for rel_service in relation:
                if rel_service.split(':')[0] == service:
                    self.relations.remove(relation)
                    break

    def relate(self, *args):
        if len(args) < 2:
            raise LookupError('Need at least two services:relation')

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
        if [a, b] not in self.relations and [b, a] not in self.relations:
            self.relations.append([a, b])
            if self.deployed:
                juju(['add-relation'] + [a, b])

    def unrelate(self, *args):
        if len(args) != 2:
            raise LookupError('Need exactly two service:relations')

        for srv_rel in args:
            if not ':' in srv_rel:
                raise ValueError('All relations must be explicit, ' +
                                 'service:relation')
        relation = list(args)
        for rel in relation, reversed(relation):
            if rel in self.relations:
                relation = rel
                break
        else:
            raise ValueError('Relation does not exist')

        self.relations.remove(relation)
        if self.deployed:
            juju(['remove-relation'] + relation)

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
                opts.append("%s=%s" % (k, v))
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

    def setup(self, timeout=600, cleanup=True):
        """Deploy the workload.

        :param timeout: Amount of time to wait for deployment to complete.
        :param cleanup: Set to False to leave the generated deployer file
            on disk. Useful for debugging.

        """
        if not self.deployer:
            raise NameError('Path to juju-deployer is not defined.')

        _, s = tempfile.mkstemp(prefix='amulet-juju-deployer-', suffix='.json')
        with open(s, 'w') as f:
            f.write(json.dumps(self.schema()))

        try:
            with unit_timesout(timeout):
                subprocess.check_call([
                    os.path.expanduser(self.deployer),
                    '-W', '-L',
                    '-c', s,
                    '-e', self.juju_env,
                    '-t', str(timeout + 100),  # ensure timeout before deployer
                    self.juju_env,
                ], cwd=self.deployer_dir)
            self.deployed = True
        except subprocess.CalledProcessError:
            raise
        finally:
            if cleanup:
                os.remove(s)

        if not self.deployed:
            raise Exception('Deployment failed for an unknown reason')

        if self.deployed:
            self.sentry = Talisman(self.services)

    def deployer_map(self, services, relations):
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

    def cleanup(self):
        shutil.rmtree(self.deployer_dir)
