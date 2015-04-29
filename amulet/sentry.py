import glob
import json
import os
import subprocess
import time

import pkg_resources

from . import waiter
from . import helpers


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

    def juju_agent(self, timeout):
        raise NotImplemented()


class UnitSentry(Sentry):
    @classmethod
    def fromunit(cls, unit):
        pass

    @classmethod
    def fromunitdata(cls, unit, unit_data):
        address = unit_data['public-address']
        unitsentry = cls(address)
        d = unitsentry.info = unit_data
        d['unit_name'] = unit
        d['service'], d['unit'] = unit.split('/')
        unitsentry.upload_scripts()
        return unitsentry

    def upload_scripts(self):
        source = pkg_resources.resource_filename(
            'amulet', os.path.join('unit-scripts', 'amulet'))
        dest = '/tmp/amulet'
        self.run('mkdir -p -m a=rwx {}'.format(dest))
        # copy one at a time b/c `juju scp -r` doesn't work (currently)
        for f in glob.glob(os.path.join(source, '*.py')):
            cmd = "juju scp {} {}:{}".format(
                os.path.join(source, f),
                self.info['unit_name'], dest)
            subprocess.check_call(cmd.split())

    def _fs_data(self, path):
        return self._run_unit_script("filesystem_data.py {}".format(path))

    def file_stat(self, filename):
        return self._fs_data(filename)

    def file_contents(self, filename):
        output, return_code = self._run('cat {}'.format(filename))
        if return_code == 0:
            return output
        else:
            raise IOError(output)

    def directory_stat(self, path):
        return self._fs_data(path)

    def directory_listing(self, path):
        return self._run_unit_script("directory_listing.py {}".format(path))

    def run(self, command):
        output, code = self._run(command)
        return output.strip(), code

    def _run(self, command, unit=None, timeout=300):
        """
        Run a command against an individual unit.

        The timeout defaults to 5m to match the `juju run` command, but can
        be increased to wait for other running hook contexts to complete.
        """
        unit = unit or self.info['unit_name']
        cmd = [
            'juju', 'run',
            '--unit', unit,
            '--timeout', "%ds" % timeout,
            command
        ]
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = p.communicate()
        output = stdout if p.returncode == 0 else stderr
        return output.decode('utf8'), p.returncode

    def _run_unit_script(self, cmd, timeout=300):
        cmd = "/tmp/amulet/{}".format(cmd)
        output, return_code = self._run(cmd, timeout=timeout)
        if return_code == 0:
            return json.loads(output)
        else:
            raise IOError(output)

    def juju_agent(self, timeout=300):
        return self._run_unit_script("juju_agent.py", timeout)

    def relation(self, from_rel, to_rel):
        this_unit = '{service}/{unit}'.format(**self.info)
        to_service, to_relation = to_rel.split(':')
        r_ids, _ = self._run('relation-ids {}'.format(from_rel))
        r_units = []
        for r_id in r_ids.split():
            r_units.extend(self._run(
                'relation-list -r {}'.format(r_id))[0].split())
        r_units = [u for u in r_units if u.split('/')[0] == to_service]
        for r_unit in r_units:
            r_ids, _ = self._run(
                'relation-ids {}'.format(to_relation), unit=r_unit)
            l_units = []
            for r_id in r_ids.split():
                l_units.extend(self._run(
                    'relation-list -r {}'.format(r_id),
                    unit=r_unit)[0].split())
                if this_unit in l_units:
                    break
            output, _ = self._run(
                'relation-get -r {} - {} --format json'.format(
                    r_id, this_unit), unit=r_unit)
            return json.loads(output)

        raise Exception('Relationship not found')


# Possibly use to build out instead of having code in setup()?
class Talisman(object):
    def __init__(self, services, rel_sentry='relation-sentry', juju_env=None):
        self.unit = {}
        self.service = {}

        if not juju_env:
            juju_env = helpers.default_environment()

        status = self.wait_for_status(juju_env, services)

        for service in services:
            if service not in status['services']:
                continue  # Raise something?

            service_status = status['services'][service]

            if 'units' not in service_status:
                continue

            for unit in service_status['units']:
                unit_data = service_status['units'][unit]
                self.unit[unit] = UnitSentry.fromunitdata(unit, unit_data)
                if 'subordinates' in unit_data:
                    for sub in unit_data['subordinates']:
                        if sub.split('/')[0] not in services:
                            continue
                        subdata = unit_data['subordinates'][sub]
                        self.unit[sub] = UnitSentry.fromunitdata(sub, subdata)

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
        public-address assigned and are in a 'started' state.

        Some substrates (like Amazon) will return a public-address while the
        machine is still allocating, so it's necessary to also check the
        agent-state to see if the unit is ready.

        Raises if a unit reaches error state, or if public-address not
        available for all units before timeout expires.

        """
        try:
            with helpers.timeout(timeout):
                while True:
                    ready = True
                    status = waiter.status(juju_env)
                    for service in services:
                        if 'units' not in status['services'][service]:
                            continue
                        for unit, unit_dict in \
                                status['services'][service]['units'].items():
                            if 'error' == unit_dict.get('agent-state'):
                                raise Exception('Error on unit {}: {}'.format(
                                    unit, unit_dict.get('agent-state-info')))
                            if 'public-address' not in unit_dict:
                                ready = False
                            if 'started' != unit_dict.get('agent-state'):
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
        """
        wait_for_status, called by __init__, blocks until units are in a
        started state. Here we wait for a unit to finish any running hooks.
        When the unit is done, juju_agent will return {}. Otherwise, it returns
        a dict with the name of the running hook.

        Raises an error if the timeout is exceeded.
        """
        ready = False
        try:
            with helpers.timeout(timeout):
                while not ready:
                    for unit in self.unit.keys():
                        status = self.unit[unit].juju_agent(timeout=timeout)

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
