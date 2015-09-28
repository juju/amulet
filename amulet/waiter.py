import sys
import yaml

from .helpers import (
    TimeoutError,
    default_environment,
    timeout_gen,
    juju,
    JujuVersion,
)

SUCCESS_STATES = ['started']


def wait(*args, **kwargs):
    """Wait until all criteria is met for a given juju environment

    When run without parameters the following defaults are used:
      - juju_env = os.environ['JUJU_ENV']
      - timeout = 300 (5m)
      - Wait will pause execution and wait for ALL units to move to a non-error
      state.

    You can specify which service or units you want to wait for by passing them
    as arguments:

      amulet.wait('service_a', 'service_a/1')

    """
    import os

    if not 'juju_env' in kwargs:
        kwargs['juju_env'] = \
            os.environ.get('JUJU_ENV') or default_environment()

    if not 'timeout' in kwargs:
        kwargs['timeout'] = 300

    for i in timeout_gen(kwargs['timeout']):
        try:
            raise_for_state(*args, juju_env=kwargs['juju_env'])
            return True
        except StateError:
            pass


def raise_for_state(*args, **kwargs):
    status = state(*args, **kwargs)

    for service in status:
        for unit in status[service]:
            if not status[service][unit] in SUCCESS_STATES:
                raise StateError("%s: %s" % (unit, status[service][unit]))


class StateError(Exception):
    def __init__(self, value="A unit is in a pending or error state"):
        self.value = value


# Move these to another module?
def _get_gojuju_status(environment=None):
    return _get_pyjuju_status(environment)


# Move these to another module?
def _get_pyjuju_status(environment=None):
    cmd = ['status', '--format', 'yaml']
    if environment:
        cmd.extend(['-e', environment])

    try:
        status_yml = juju(cmd)
    except TimeoutError:
        raise
    except:
        raise Exception('Unable to query status for %s' % environment)

    return yaml.safe_load(status_yml)


def get_state(data):
    states = ['life', 'relations-error', 'agent-state']
    for state_key in states:
        if state_key in data:
            return str(data[state_key])


def status(juju_env=None):
    version = JujuVersion()

    if not juju_env:
        raise KeyError('No juju_env set')

    try:
        if version.major == 0:
            juju_status = _get_pyjuju_status(juju_env)
        else:
            juju_status = _get_gojuju_status(juju_env)
    except TimeoutError:
        raise
    except:
        raise

    return juju_status


def state(*args, **kwargs):
    output = {}

    if not 'juju_env' in kwargs:
        raise KeyError('No juju_env set')

    juju_env = kwargs['juju_env']

    try:
        juju_status = status(juju_env)
    except TimeoutError:
        raise
    except:
        return output

    if not args:
        args = [service for service in juju_status['services']]

    for arg in args:
        service, unit = arg.split('/') if '/' in arg else [arg, None]
        if not service in juju_status['services']:
            raise ValueError('%s is not in the deployment yet' % arg)

        if not service in output:
            output[service] = {}

        if not 'units' in juju_status['services'][service]:
            # Probably a subordinate
            if 'subordinate-to' in juju_status['services'][service]:
                del output[service]
            continue

        # Use potential recurive + mergedicts?
        # http://stackoverflow.com/a/7205672/196832
        units = juju_status['services'][service]['units']
        if unit:
            output[service][unit] = get_state(units['/'.join([service, unit])])
        else:
            for unit_name in units:
                unit = unit_name.split('/')[1]
                s = get_state(units['/'.join([service, unit])])
                output[service][unit] = s

    return output


def setup_parser(parent):
    def wait_cmd(args):
        try:
            wait(*args.services, **vars(args))
        except TimeoutError:
            sys.stderr.write('Timeout criteria was met\n')
            sys.exit(124)
        except:
            sys.stderr.write('Unexpected error occurred\n')
            raise

        sys.exit(0)

    parser = parent.add_parser('wait', help="Wait until criteria is met")
    parser.add_argument('-e', '--environment', dest='juju_env',
                        help="Juju environment")
    parser.add_argument('-t', '--timeout', help="Timeout in seconds", type=int,
                        default=300)
    parser.add_argument('services', nargs='*',
                        help="What services or units to wait on")
    parser.set_defaults(func=wait_cmd)
