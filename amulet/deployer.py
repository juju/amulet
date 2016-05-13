import base64
import contextlib
import json
import logging
import os
import shlex
import subprocess
import warnings
import yaml

from path import path
from path import tempdir

from . import actions
from .helpers import (
    default_environment,
    juju,
    timeout as unit_timesout,
    JUJU_VERSION,
)
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
    """A Juju workload.

    Use this class to add, configure, relate, and deploy services to a
    Juju environment.

    :ivar Deployment.sentry: A :class:`amulet.sentry.Talisman` instance that
        becomes available after a call to :meth:`setup` (before that,
        :attr:`sentry` is ``None``.

    """
    log = logger

    def __init__(self, juju_env=None, series='precise',
                 juju_deployer='juju-deployer', **kw):
        """Initialize a deployment.

        :param juju_env: Name of the Juju enviroment in which to deploy. If
            None, the default environment is used.
        :param series: The default series of charms to deploy.
        :param juju_deployer: Path to juju_deployer binary to use for the
            deployment.

        """
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
        """Create a :class:`Deployment` object from a bundle file.

        :param bundle_file: Path to the bundle file.
        :param deployment_name: Name of the deployment to use. Useful for
            old-style bundle files that contain multiple named deployments.
        :return: A new :class:`Deployment` object.

        """
        deployment = cls()
        bundle_file = path(bundle_file)
        deployment.load_bundle_file(bundle_file, deployment_name)
        return deployment

    def load_bundle_file(self, bundle_file, deployment_name=None):
        """Load a bundle file from disk.

        :param bundle_file: Path to the bundle file.
        :param deployment_name: Name of the deployment to use. Useful for
            old-style bundle files that contain multiple named deployments.

        """
        with open(bundle_file, 'r') as stream:
            contents = yaml.safe_load(stream)
        return self.load(contents, deployment_name)

    def load(self, deploy_cfg, deployment_name=None):
        """Load an existing deployment schema (bundle) dictionary.

        :param deploy_cfg: The bundle dictionary.
        :param deployment_name: Name of the deployment to use. Useful for
            old-style bundle files that contain multiple named deployments.

        """
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
        """Add a new service to the deployment schema.

        :param service_name: Name of the service to deploy.
        :param charm: Name of the charm to deploy for this service. If None,
            defaults to ``service_name``.
        :param units: Number of units to deploy.
        :param constraints: Dictionary of service constraints.
        :param branch: TODO
        :param placement: Placement directive for this service. Examples:

            "1" - Deploy to machine 1
            "lxc:1" - Deploy to lxc container on machine 1
            "lxc:wordpress/0 - Deploy to lxc container on first wordpress unit

        :param series: Series of charm to deploy, e.g. precise, trusty, xenial

        Example::

            import amulet
            d = amulet.Deployment()
            d.add('wordpress')
            d.add('second-wp', charm='wordpress')
            d.add('personal-wp', charm='~marcoceppi/wordpress', units=2)

        """
        if self.deployed:
            raise NotImplementedError('Environment already setup')

        if service_name in self.services:
            raise ValueError('Service is already set to be deployed')

        service = self.services[service_name] = {}
        service['series'] = series or self.series

        charm = self.charm_cache.fetch(
            service_name, charm, branch=branch, series=service['series'])

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
        """Add more units of an existing service after deployment.

        :param service: Name of service to which units will be added.
        :param units: Number of units to add.
        :param target: Placement directive for the added unit(s).

        Example::

            import amulet
            d = amulet.Deployment()
            d.add('wordpress')
            try:
                d.setup(timeout=900)
            except amulet.helpers.TimeoutError:
                # Setup didn't complete before timeout
                pass
            d.add_unit('wordpress')
            d.add_unit('wordpresss', units=2)
            d.add_unit('wordpresss', target="lxc:1")

        """
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
            self.sentry = Talisman(self.services, juju_env=self.juju_env)

    def remove_unit(self, *units):
        """Remove (destroy) one or more already-deployed units.

        :param units: One or more units in the form <service>/<unit_num>,
            e.g. "wordpress/0", passed as \*args.

        """
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
        """Remove (destroy) one or more already-deployed services.

        :param services: One or more service names passed as \*args.

        """
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
        """Remove (destroy) one or more already-deployed services or units.

        :param units_or_services: One or more service or unit names passed
            as \*args.

        """
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
        """Relate two or more services together.

        If more than two arguments are given, the first service is related
        to each of the others.

        :param args: Services to relate, in the form
            "service_name:relation_name".

        Example::

            import amulet
            d = amulet.Deployment()
            d.add('postgresql')
            d.add('mysql')
            d.add('wordpress')
            d.add('mediawiki')
            d.add('discourse')
            d.relate('postgresql:db-admin', 'discourse:db')
            d.relate('mysql:db', 'wordpress:db', 'mediawiki:database')
            # previous command is equivalent too:
            d.relate('mysql:db', 'wordpress:db')
            d.relate('mysql:db', 'mediawiki:database')

        """
        if len(args) < 2:
            raise LookupError('Need at least two services:relation')

        for srv_rel in args:
            if ':' not in srv_rel:
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
        """Remove a relation between two services.

        :param args: Services to unrelate, in the form
            "service_name:relation_name".

        Example::

            import amulet
            d = amulet.Deployment()
            d.add('postgresql')
            d.add('mysql')
            d.add('wordpress')
            d.add('mediawiki')
            d.add('discourse')
            d.relate('postgresql:db-admin', 'discourse:db')
            d.relate('mysql:db', 'wordpress:db', 'mediawiki:database')
            # unrelate all the services we just related
            d.unrelate('postgresql:db-admin', 'discourse:db')
            d.unrelate('mysql:db', 'wordpress:db')
            d.unrelate('mysql:db', 'mediawiki:database')

        """
        if len(args) != 2:
            raise LookupError('Need exactly two service:relations')

        for srv_rel in args:
            if ':' not in srv_rel:
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
        """Return the deployment schema (bundle) as a dictionary.

        """
        return self._deployer_map(self.services, self.relations)

    def configure(self, service, options):
        """Change configuration options for a service (deployed or not).

        :param service: Name of service to configure.
        :param options: Dictionary of configuration settings.

        Example::

            import amulet
            d = amulet.Deployment()
            d.add('postgresql')
            d.configure('postgresql', {
                'autovacuum': True,
                'cluster_name': 'cname',
            })

        """
        for k, v in options.items():
            include_token = 'include-base64://'
            if type(v) is str and v.startswith(include_token):
                v = v.replace(include_token, '')
                with open(os.path.join(os.getcwd(), 'tests', v)) as f:
                    v = base64.b64encode(f.read())
                service['options'][k] = v

        if self.deployed:
            juju_set_cmd = 'set' if JUJU_VERSION.major == 1 else 'set-config'
            opts = [juju_set_cmd, service]
            for k, v in options.items():
                opts.append("%s=%s" % (k, v))
            return juju(opts)

        if service not in self.services:
            raise ValueError('Service has not yet been described')

        if 'options' not in self.services[service]:
            self.services[service]['options'] = options
        else:
            self.services[service]['options'].update(options)

    def expose(self, service):
        """Expose a service.

        If the service is already deployed it will be exposed immediately,
        otherwise it will be exposed when deployed.

        :param service: Name of the service to expose.

        Example::

            import amulet
            d = amulet.Deployment()
            d.add('varnish')
            d.expose('varnish')

        """
        if self.deployed:
            return juju(['expose', service])

        if service not in self.services:
            raise ValueError('%s has not yet been described' % service)
        self.services[service]['expose'] = True

    @contextlib.contextmanager
    def _deploy_w_timeout(self, timeout):
        """Sets timeout and tmp working directory for wrapped block.

        If successful, sets instance.deployed.

        :param timeout: Amount of time to wait for deployment to complete.

        """
        deploy_dir = tempdir(prefix='amulet_deployment_')
        with deploy_dir, unit_timesout(timeout):
            yield
        self.deployed = True

    def action_defined(self, service):
        """Return list of actions defined for the service.

        :param service: Name of service for which to list actions.
        :return: List of actions, as json.

        .. deprecated:: 1.15
           Use :meth:`UnitSentry.list_actions instead.`

        """
        warnings.warn(
            'Deployment.action_defined is deprecated, use '
            'UnitSentry.list_actions instead.',
            DeprecationWarning
        )

        if service not in self.services:
            raise ValueError(
                'Service needs to be added before listing actions.')

        return actions.list_actions(service)

    def action_do(self, unit, action, action_args=None):
        """Run action on a unit and return the result UUID.

        :param unit: Unit on which to run action, e.g. "wordpress/0"
        :param action: Name of action to run.
        :param action_args: Dictionary of action parameters.
        :return str: The action UUID.

        .. deprecated:: 1.15
           Use :meth:`UnitSentry.run_action instead.`

        """
        warnings.warn(
            'Deployment.action_do is deprecated, use '
            'UnitSentry.run_action instead.',
            DeprecationWarning
        )

        return actions.run_action(unit, action, action_args=action_args)

    def action_fetch(
            self, action_id, timeout=600, raise_on_timeout=False,
            full_output=False):
        """Fetch results for an action.

        If the timeout expires and the action is still not complete, an
        empty dictionary is returned. To raise an exception instead, pass
        ``raise_on_timeout=True``.

        By default, only the 'results' dictionary of the action output is
        returned. To get the full action output instead, pass
        ``full_output=True``.

        :param action_id: UUID of the action.
        :param timeout: Length of time to wait for an action to complete.
        :param raise_on_timeout: If True, :class:`amulet.helpers.TimeoutError`
            will be raised if the action is still running when the timeout
            expires.
        :param full_output: If True, returns the full output from the action.
            If False, only the 'results' dictionary from the action output is
            returned.
        :return: Action results, as json.

        """
        return actions.get_action_output(
            action_id, timeout=timeout, raise_on_timeout=raise_on_timeout,
            full_output=full_output
        )
    get_action_output = action_fetch

    def setup(self, timeout=600, cleanup=True):
        """Deploy the workload.

        If timeout expires before the deployment completes, raises
            :class:`amulet.helpers.TimeoutError`.

        :param timeout: Amount of time to wait for deployment to complete.
            If environment variable AMULET_SETUP_TIMEOUT is set, it overrides
            this value.
        :param cleanup: Set to False to leave the generated deployer file
            on disk. Useful for debugging.

        Example::

            import amulet
            d = amulet.Deployment()
            d.add('wordpress')
            d.add('mysql')
            d.configure('wordpress', debug=True)
            d.relate('wordpress:db', 'mysql:db')
            try:
                d.setup(timeout=900)
            except amulet.helpers.TimeoutError:
                # Setup didn't complete before timeout
                pass

        """
        timeout = int(os.environ.get('AMULET_SETUP_TIMEOUT') or timeout)

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

            with self._deploy_w_timeout(timeout):
                subprocess.check_call(shlex.split(cmd))

        self.sentry = Talisman(
            self.services, timeout=timeout, juju_env=self.juju_env)
        if cleanup is False:
            tmpdir.makedirs()
            (tmpdir / 'deployer-schema.json').write_text(schema_json)

    def _deployer_map(self, services, relations):
        return {
            self.juju_env: {
                'series': self.series,
                'services': self.services,
                'relations': self._build_relations()
            }
        }

    def _build_relations(self):
        relations = []
        for rel in self.relations:
            relations.append(rel)

        return relations
