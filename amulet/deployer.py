
import os
import yaml

_services = {}
_relations = {}
_schema = {}
_series = 'precise'
_environment = None
_interfaces = []


def deploy(service, charm=None):
    # Do charm revision look ups?
    if service in get_services():
        raise ValueError('Service is already set to be deployed')
    _services[service] = {'branch': charm or 'lp:charms/%s' % service}


def relate(from_charm, to_charm):
    if not from_charm in relations:
        relations[from_charm] = []

    relations[from_charm].append(to_charm)


def series(series):
    if default_series:
        _series = series
    else:
        return _series


def _get_default_environment():
    try:
        env_file = open(os.path.expanduser('~/.juju/environments.yaml'), 'r')
        env = yaml.safe_load(env_file)
    except:
        raise Exception('Unable to parse ~/.juju/environments.yaml')
    else:
        if 'default' in env:
            return env.default
        else if count(env.environments) == 1:
            return env.environments[0]

        raise new ValueError('No default environment configured')


def set_environment(env):
    _environment = env


def get_services():
    return _services


def get_relations():
    return _relations


def get_schema():
    return _generate_deployer_map(get_services(), get_relations())


def configure(service, options={}):
    if service not in get_services():
        raise ValueError('Service has not yet been described')
    _services[service]['options'] = options


def setup(timeout=300):
    pass


def _generate_deployer_map(services, relations):
    juju_env = _environment or _get_default_environment()
    _build_relation_scaffold()
    deployer_map = {
        juju_env: {
            'series': _series,
            'services': _services,
            'relations': _get_relations()
        }
    }

def _find_common_interface(*args)


def _build_sentries(relation_data=None):
    
    pass
