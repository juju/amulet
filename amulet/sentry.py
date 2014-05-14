
import requests

from . import waiter
from . import helpers
from .charm import get_relation

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode


class SentryError(Exception):
    pass


class Sentry(object):
    def __init__(self, address, port=9001):
        self.config = {}
        self.config['address'] = 'https://%s:%s' % (address, port)

    def file(self, filename):
        return self.file_stat(filename)

    def file_stat(self, filename):
        raise NotImplemented()

    def file_contents(self, filename):
        raise NotImplemented()

    def directory(self, *args):
        return self.directory_stat(*args)

    def directory_stat(self, *args):
        raise NotImplemented()

    def directory_contents(self, *args):
        return self.directory_listing(*args)

    def directory_listing(self, *args):
        raise NotImplemented()

    def juju_agent(self):
        try:
            return self.query('/juju').json()
        except:
            return None

    def query(self, endpoint, query={}, data=None):
        return self._fetch(self.config['address'], endpoint, query, data)

    def _fetch(self, address, endpoint, query={}, data=None):
        url = "%s/%s?%s" % (address, endpoint, urlencode(query))
        if data:
            return requests.post(url, data=data, verify=False)
        else:
            return requests.get(url, verify=False)


class UnitSentry(Sentry):
    @classmethod
    def fromunit(cls, unit):
        pass

    @classmethod
    def fromunitdata(cls, unit, unit_data, sentry, port=9001):
        address = unit_data['public-address']
        unitsentry = cls(address)
        unitsentry.info = unit_data
        unitsentry.info['service'] = unit.split('/')[0]
        unitsentry.info['unit'] = unit.split('/')[1]
        unitsentry.config['sentry'] = 'https://%s:%s' % (sentry, port)
        return unitsentry

    def file_stat(self, filename):
        r = self._fetch_filesystem('/file', {'name': filename})
        return r.json()

    def _fetch_filesystem(self, endpoint, params):
        r = self.query(endpoint, params)
        if r.status_code == 404:
            raise IOError('%s does not exist on unit' % params['name'])
        elif r.status_code != 200:
            raise SentryError('API returned the following: %s' % r.status_code)

        return r

    def file_contents(self, filename):
        r = self._fetch_filesystem('/file/contents', {'name': filename})
        return r.text

    def directory_stat(self, path):
        r = self._fetch_filesystem('/directory', {'name': path})
        return r.json()

    def directory_listing(self, path):
        r = self._fetch_filesystem('/directory/contents', {'name': path})
        return r.json()

    def run(self, command):
        r = self.query('/run', data=command)
        results = r.json()
        return results['output'], results['code']

    #d.sentry.unit[].relation('db', 'mysql:db')
    def relation(self, from_rel, to_rel):
        # Build possible mappings, find the map, produce results
        potential_rel = ['%s:%s' % (self.info['service'], from_rel), to_rel]
        rel_data = get_relation(self.info['service'], from_rel)
        relations = ['-'.join([rel_data[0],
                     "-".join(potential_rel).replace(':', '_')])]
        potential_rel.reverse()
        relations.append('-'.join([rel_data[0],
                         "-".join(potential_rel).replace(':', '_')]))
        for relation in relations:
            r = self._fetch(self.config['sentry'],
                            '/relation/%s/%s' % (relation, self.info['unit']))
            if r.status_code == 200:
                return r.json()

        raise Exception('Relationship not found')


# Possibly use to build out instead of having code in setup()?
class Talisman(object):
    def __init__(self, services, rel_sentry='relation-sentry', juju_env=None):
        self.unit = {}
        self.service = {}

        if not juju_env:
            juju_env = helpers.default_environment()

        status = self.wait_for_status(juju_env, services)
        if rel_sentry in status['services']:
            rel_sentry_units = status['services'][rel_sentry]['units']
            rel_sentry_unit = rel_sentry_units['/'.join([rel_sentry, '0'])]
            rel_sentry_addr = rel_sentry_unit['public-address']
        else:
            raise Exception('No relationship sentry found')

        for service in services:
            if not service in status['services']:
                continue  # Raise something?

            # self.sentry.service[service] = ServiceSentry()

            service_status = status['services'][service]

            if not 'units' in service_status:
                continue  # It's a subordinate

            for unit in service_status['units']:
                unit_data = service_status['units'][unit]
                self.unit[unit] = UnitSentry.fromunitdata(unit, unit_data,
                                                          rel_sentry_addr)

    def __getitem__(self, service):
        """Return the UnitSentry object(s) for ``service``

        :param service: A string in one of two forms::
            "service_name"
            "service_name/unit_num"

        If the first form is used, a list (possibly empty) of all the
        UnitSentry objects for that service is returned.

        If the second form is used, a single object, the UnitSentry for
        the specified unit, is returned.

        Examples::

            >>> d
            <amulet.deployer.Deployment object at 0x7fac83ce8438>
            >>> d.schema()['local']['services']['meteor']['num_units']
            2
            >>> # get UnitSentry for specific unit
            >>> meteor_0 = d.sentry['meteor/0']
            >>> print(meteor_0.info['service'], meteor_0.info['unit'])
            meteor 0
            >>> # get all UnitSentry objects for a service
            >>> for sentry in d.sentry['meteor']:
            ...     print(sentry.info['service'], sentry.info['unit'])
            ...
            meteor 1
            meteor 0
            >>>

        """
        single_unit = '/' in service

        def match(service, unit_name):
            if single_unit:
                return service == unit_name
            return service == unit_name.split('/')[0]

        unit_sentries = [unit_sentry
                         for unit_name, unit_sentry in self.unit.items()
                         if match(service, unit_name)]

        if single_unit and unit_sentries:
            return unit_sentries[0]

        return unit_sentries

    def wait_for_status(self, juju_env, services, timeout=300):
        """Return env status, but only after all units have a
        public-address assigned.

        Raises if a unit reaches error state, or if public-address not
        available for all units before timeout expires.

        """
        try:
            with helpers.timeout(timeout):
                while True:
                    ready = True
                    status = waiter.status(juju_env)
                    for service in services:
                        if not 'units' in status['services'][service]:
                            continue
                        for unit, unit_dict in \
                                status['services'][service]['units'].items():
                            if 'error' == unit_dict.get('agent-state'):
                                raise Exception('Error on unit {}: {}'.format(
                                    unit, unit_dict.get('agent-state-info')))
                            if 'public-address' not in unit_dict:
                                ready = False
                    if ready:
                        return status
        except helpers.TimeoutError:
            raise helpers.TimeoutError(
                'public-address not set for'
                'all units after {}s'.format(timeout))
        except:
            raise

    def wait(self, timeout=300):
        #for unit in self.unit:
        ready = False
        try:
            with helpers.timeout(timeout):
                # Make sure we're in a 'started' state across the board
                waiter.wait(timeout=timeout)
                while not ready:
                    for unit in self.unit.keys():
                        status = self.unit[unit].juju_agent()
                        # Check if we have a hook key and it's not None
                        if status is None:
                            ready = False
                            break
                        if 'hook' in status and status['hook']:
                            ready = False
                            break
                        else:
                            ready = True
        except:
            raise

    def _sync(self):
        pass


class ServiceSentry(Sentry):
    pass
