
import copy
import yaml

TPLS = {
    'juju-core': {
        'machines': {
            'agent-state': 'started',
            'agent-version': '1.11.0',
            'dns-name': 'xxx',
            'instance-id': 'i-xxx',
            'series': 'precise',
        }, 'services': {
            'charm': 'cs:precise/%s-x',
            'exposed': False,
        }, 'units': {
            'agent-state': 'pending',
            'agent-version': '1.11.0',
            'machine': '',
            'public-address': 'xxx',
        }
    }, 'juju': {
        'machines': {
            'agent-state': 'running',
            'dns-name': 'xxx',
            'instance-id': 'i-xxx',
            'instance-state': 'running',
        }, 'services': {
            'charm': 'cs:precise/%s-x',
            'relations': {},
        }, 'units': {
            'agent-state': 'pending',
            'public-address': 'xxx',
            'machine': '',
        }
    }
}


class JujuStatus(object):
    def __init__(self, version='juju-core'):
        self.status = {'machines': {}, 'services': {}}
        self.version = version
        self.add_machine()

    def add(self, service, state='started', relation_error=None, dying=False):
        if not service in self.status['services']:
            stpl = self.get_template('services')
            stpl['charm'] = stpl['charm'] % service
            stpl['units'] = {}
            self.status['services'][service] = stpl

        if dying and self.version == 'juju-core':
            self.status['services'][service]['life'] = 'dying'

        machine = self.add_machine()
        unit = "%s/%s" % (service,
                          len(self.status['services'][service]['units']))
        utpl = self.get_template('units')
        utpl['machine'] = machine
        utpl['agent-state'] = state

        if relation_error:
            if self.version == 'juju':
                utpl['relation-error'] = relation_error
            else:
                utpl['state'] = 'error %s' % relation_error

        self.status['services'][service]['units'][unit] = utpl

    def add_machine(self):
        tpl = self.get_template('machines')
        machine = len(self.status['machines'])
        if self.version == 'juju-core':
            machine = str(machine)

        self.status['machines'][machine] = tpl
        return machine

    def get_template(self, key, version=None):
        global TPLS
        if not version:
            version = self.version

        return copy.deepcopy(TPLS[version][key])

    def __str__(self):
        return yaml.dump(self.status, default_flow_style=False)
