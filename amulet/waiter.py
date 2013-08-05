
import os
import sys
import yaml
import subprocess
from . import helpers

from .helpers import JujuVersion, TimeoutError

SUCESS_STATES = ['started']


# Move these to another module?
def _get_gojuju_status(environment=None):
    return _get_pyjuju_status(environment)


# Move these to another module?
def _get_pyjuju_status(environment=None):
    cmd = ['juju', 'status']
    if environment:
        cmd.extend(['-e', environment])

    try:
        status_yml = subprocess.check_output(cmd)
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
    version = helpers.JujuVersion()

    if not 'juju_env' in kwargs:
        raise KeyError('No juju_env set')

    juju_env = kwargs['juju_env']

    try:
        if version.major == 0:
            juju_status = _get_pyjuju_status(juju_env)
        else:
            juju_status = _get_gojuju_status(juju_env)
    except TimeoutError:
        raise
    except Exception as e:
        raise

    return juju_status


def state(*args, **kwargs):
    output = {}
    version = helpers.JujuVersion()
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

        # Use potential recurive + mergedicts?
        # http://stackoverflow.com/a/7205672/196832
        units = juju_status['services'][service]['units']
        if unit:
            output[service][unit] = get_state(units['/'.join([service, unit])])
        else:
            for unit_name in units:
                unit = unit_name.split('/')[1]
                state = get_state(units['/'.join([service, unit])])
                output[service][unit] = state

    return output


def setup_parser(parent):
    from . import wait

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
