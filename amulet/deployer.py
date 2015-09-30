import base64
import contextlib
import json
import logging
import os
import shlex
import subprocess
import yaml

from path import path
from path import tempdir

from .helpers import default_environment, juju, timeout as unit_timesout
from .sentry import Talisman
from .charm import CharmCache

logger = logging.getLogger(__name__)


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


class Deployment(object):
    log = logger

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
        self.deployer = path(juju_deployer)

        if 'JUJU_TEST_CHARM' in os.environ:
            self.charm_name = os.environ['JUJU_TEST_CHARM']

        self.charm_cache = CharmCache(self.charm_name)

    @classmethod
    def from_bundle(cls, bundle_file, deployment_name=None):
        deployment = cls()
        bundle_file = path(bundle_file)
        deployment.load_bundle_file(bundle_file, deployment_name)
        return deployment

    def load_bundle_file(self, bundle_file, deployment_name=None):
        with open(bundle_file, 'r') as stream:
            contents = yaml.safe_load(stream)
        return self.load(contents, deployment_name)

    def load(self, deploy_cfg, deployment_name=None):
        if deployment_name is None and 'services' in deploy_cfg:
            # v4 format
            schema = deploy_cfg
        else:
            # v3 format
            schema = deploy_cfg.get(deployment_name, None) \
                or next(iter(deploy_cfg.values()))
        self.series = schema.get('series', self.series)
        self.relations = schema.get('relations', [])
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
                branch=service_config.get('branch', None),
                constraints=constraints,
                placement=service_config.get('to', None),
                series=self.series
            )

            if service_config.get('options'):
                self.configure(service, service_config['options'])

            if service_config.get('expose'):
                self.expose(service)

    def add(self, service_name,
            charm=None,
            units=1,
            constraints=None,
            branch=None,
            placement=None,
            series=None):

        if self.deployed:
            raise NotImplementedError('Environment already setup')

        if service_name in self.services:
            raise ValueError('Service is already set to be deployed')

        service = self.services[service_name] = {}

        charm = self.charm_cache.fetch(
            service_name, charm, branch=branch, series=series or self.series)

        if charm.subordinate:
            for rtype in ['provides', 'requires']:
                try:
                    rels = getattr(charm, rtype)
                    for relation in rels:
                        rel = rels[relation]
                        if 'scope' in rel and rel['scope'] == 'container':
                            self.subordinates.append('%s:%s' %
                                                     (service_name, relation))
                except:  # @@ why is this diaper here?
                    pass

        source = charm.url and {'charm': charm.url} \
            or {'branch': charm.code_source['location']}

        service.update(source)

        service['num_units'] = units
        if placement is not None:
            service['to'] = placement

        if 'JUJU_TEST_CONSTRAINTS' in os.environ:
            env_constraints = {}
            for c in os.environ['JUJU_TEST_CONSTRAINTS'].split():
                try:
                    k, v = c.split('=')
                    env_constraints[k] = v
                except:
                    raise ValueError(
                        'Invalid constraint in JUJU_TEST_CONSTRAINTS: '
                        '%s' % (c))
            if constraints is not None:
                env_constraints.update(constraints)
            constraints = env_constraints

        if constraints is not None:
            if not isinstance(constraints, dict):
                raise ValueError('Constraints must be specified as a dict')

            r = ['%s=%s' % (K, V) for K, V in constraints.items()]
            service['constraints'] = " ".join(r)

        return service

    def add_unit(self, service, units=1, target=None):
        if not isinstance(units, int) or units < 1:
            raise ValueError('Only positive integers can be used for units')
        if target is not None and units != 1:
            raise ValueError(
                "Can't deploy more than one unit when specifying a target.")
        if service not in self.services:
            raise ValueError('Service needs to be added before you can scale')

        self.services[service]['num_units'] = \
            self.services[service].get('num_units', 1) + units

        if self.deployed:
            args = ['add-unit', service, '-n', str(units)]
            if target is not None:
                args.extend(["--to", target])
            juju(args)
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

    @contextlib.contextmanager
    def deploy_w_timeout(self, timeout):
        """
        :param timeout: Amount of time to wait for deployment to complete.

        Sets timeout and tmp working directory for wrapped block. If
        successful, sets instance.deployed.

        """
        deploy_dir = tempdir(prefix='amulet_deployment_')
        with deploy_dir, unit_timesout(timeout):
            yield
        self.deployed = True

    def action_defined(self, service):
        """
        :param service: Name of service to get list of defined actions for.

        Returns the list of actions defined for the service.
        """
        if service not in self.services:
            raise ValueError(
                'Service needs to be added before listing actions.')
        raw = juju(['action', 'defined', service, '--format', 'json'])
        return json.loads(raw)

    def action_do(self, unit, action, action_args={}):
        """
        :param unit: Unit to run action on.
        :param action: Action to run.
        :param action_args: Action parameters.

        Runs specified action on specified unit and returns the uuid to fetch
        results by.

        """
        if '/' not in unit:
            raise ValueError('%s is not a unit' % unit)
        cmd = ['action', 'do', unit, action, '--format', 'json']
        for key, value in action_args.items():
            cmd += ["%s=%s" % (str(key), str(value))]
        result = juju(cmd)
        action_result = json.loads(result)
        results_id = action_result["Action queued with id"]
        return results_id

    def action_fetch(self, action_id, timeout=600):
        """
        :param action_id: Id of the action to fetch results for.
        """
        cmd = ['action', 'fetch', action_id, '--format', 'json']
        if timeout is not None:
            cmd += ["--wait", str(timeout)]
        raw = juju(cmd)
        result = json.loads(raw)
        status = result['status']
        if status == 'completed':
            if 'results' in result:
                return result['results']
        return {}

    def setup(self, timeout=600, cleanup=True):
        """Deploy the workload.

        :param timeout: Amount of time to wait for deployment to complete.
        :param cleanup: Set to False to leave the generated deployer file
            on disk. Useful for debugging.

        """
        if not self.deployer:
            raise NameError('Path to juju-deployer is not defined.')

        with tempdir(prefix='amulet-juju-deployer-') as tmpdir:
            schema_json = json.dumps(self.schema(), indent=2)
            self.log.debug("Deployer schema\n%s", schema_json)

            schema_file = tmpdir / 'deployer-schema.json'
            schema_file.write_text(schema_json)

            cmd = "{deployer} -W {debug} -c {schema} -e {env} -t {timeout} {env}"
            cmd_args = dict(
                deployer=self.deployer.expanduser(),
                debug=(
                    '-d'
                    if self.log.getEffectiveLevel() == logging.DEBUG
                    else ''),
                schema=schema_file,
                env=self.juju_env,
                timeout=str(timeout + 100),
            )
            cmd = cmd.format(**cmd_args)
            self.log.debug(cmd)

            with self.deploy_w_timeout(timeout):
                subprocess.check_call(shlex.split(cmd))

        self.sentry = Talisman(self.services, timeout=timeout)
        if cleanup is False:
            tmpdir.makedirs()
            (tmpdir / 'deployer-schema.json').write_text(schema_json)

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
