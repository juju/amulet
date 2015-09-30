import glob
import json
import logging
import os
import subprocess
from datetime import datetime

import pkg_resources

from . import waiter
from . import helpers


# number of seconds an agent must be idle to be considered quiescent
IDLE_THRESHOLD = 30

log = logging.getLogger(__name__)


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
        output, code = self.ssh('mkdir -p -m a=rwx {}'.format(dest), raise_on_failure=True)
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

    def ssh(self, command, unit=None, raise_on_failure=False):
        """
        Run a command against an individual unit, using `juju ssh`.

        Using `juju ssh` bypasses the Juju execution queue, so it will not
        be blocked by running hooks.  Note, however, that the command is run
        as the ubuntu user instead of root.
        """
        unit = unit or self.info['unit_name']
        cmd = ['juju', 'ssh', unit, command]
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = p.communicate()
        output = stdout if p.returncode == 0 else stderr
        if raise_on_failure and p.returncode != 0:
            raise subprocess.CalledProcessError(p.returncode, cmd, output)
        return output.decode('utf8').strip(), p.returncode

    def _run_unit_script(self, cmd, working_dir=None):
        if working_dir is None:
            working_dir = '/var/lib/juju/agents/unit-{service}-{unit}/charm'.format(**self.info)
        cmd = "/tmp/amulet/{}".format(cmd)
        # XXX: Yes, we are throwing away stderr. Why? Because sudo can write
        # to stderr even when the cmd succeeds. Then, `juju ssh` combines
        # stdout and stderr before handing us the output, so we can't
        # distinguish the two. If we have stderr output mixed in with the
        # stdout of a successful cmd, json parsing will fail.
        output, return_code = self.ssh('cd {} ; sudo {} 2>/dev/null'.format(working_dir, cmd))
        if return_code == 0:
            return json.loads(output)
        else:
            raise IOError(output)

    def juju_agent(self):
        return self._run_unit_script("juju_agent.py", working_dir=".")

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
    def __init__(self, services, rel_sentry='relation-sentry', juju_env=None, timeout=300):
        self.service_names = services
        self.unit = {}
        self.service = {}

        self.juju_env = juju_env or helpers.default_environment()

        status = self.wait_for_status(self.juju_env, services, timeout)

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

    def get_status(self, juju_env=None):
        """
        Get status of all units, normalized
        to make it a bit easier to work with.
        """
        status = waiter.status(juju_env or self.juju_env)
        normalized = {}
        for service_name, service in status['services'].items():
            if 'units' not in service and 'relations' not in service:
                # ignore unrelated subordinates; they will never become ready
                continue
            normalized.setdefault(service_name, {})
            for unit_name, unit in service.get('units', {}).items():
                machine = status['machines'].get(unit.get('machine'), {})
                normalized[service_name][unit_name] = {
                    'machine-state': machine.get('agent-state'),
                    'public-address': unit.get('public-address'),
                    'workload-status': unit.get('workload-status', {}),
                    'agent-status': unit.get('agent-status', {}),
                    'agent-state': unit.get('agent-state'),
                    'agent-state-info': unit.get('agent-state-info'),
                }
                for sub_name, sub in unit.get('subordinates', {}).items():
                    sub_service = sub_name.split('/')[0]
                    normalized.setdefault(sub_service, {})
                    normalized[sub_service][sub_name] = {
                        'machine-state': machine.get('agent-state'),
                        'public-address': sub.get('public-address'),
                        'workload-status': sub.get('workload-status', {}),
                        'agent-status': sub.get('agent-status', {}),
                        'agent-state': sub.get('agent-state'),
                        'agent-state-info': sub.get('agent-state-info'),
                    }
        return normalized

    def wait_for_status(self, juju_env, services, timeout=300):
        """Return env status, but only after all units have a
        public-address assigned and are in a 'started' state.

        Some substrates (like Amazon) will return a public-address while the
        machine is still allocating, so it's necessary to also check the
        agent-state to see if the unit is ready.

        Raises if a unit reaches error state, or if public-address not
        available for all units before timeout expires.

        """
        def check_status(juju_env, services):
            status = self.get_status(juju_env)
            for service_name in services:
                if service_name not in status:
                    # ignore unrelated subordinates; they will never become ready
                    continue
                if not status[service_name]:
                    return False  # expected subordinate
                for unit_name, unit in status[service_name].items():
                    state = unit['workload-status'].get('current') or unit['agent-state']
                    message = unit['workload-status'].get('message') or unit['agent-state-info']
                    if state == 'error':
                        raise Exception('Error on unit {}: {}'.format(
                            unit_name, message))
                    if unit['machine-state'] != 'started':
                        return False
                    if not unit['public-address']:
                        return False
                    if unit['agent-state'] not in (None, 'started'):
                        return False
            return True

        for i in helpers.timeout_gen(timeout):
            if check_status(juju_env, services):
                return waiter.status(juju_env)

    def wait(self, timeout=300):
        """
        wait_for_status, called by __init__, blocks until units are in a
        started state. Here we wait for a unit to finish any running hooks.
        When the unit is done, juju_agent will return {}. Otherwise, it returns
        a dict with the name of the running hook.

        Raises an error if the timeout is exceeded.
        """
        def check_status():
            status = self.get_status()
            for service_name in self.service_names:
                service = status.get(service_name, {})
                for unit_name, unit in service.items():
                    if unit['agent-status']:
                        if unit['agent-status']['current'] != 'idle':
                            return False
                        since = datetime.strptime(unit['agent-status']['since'][:20], '%d %b %Y %H:%M:%S')
                        if (datetime.now() - since).total_seconds() < IDLE_THRESHOLD:
                            return False
                    else:
                        running_hooks = self.unit[unit_name].juju_agent()
                        if running_hooks is None or running_hooks:
                            return False
            return True

        log.info('Waiting up to %s seconds for deployment to settle...',
                 timeout)
        start = datetime.now()
        for i in helpers.timeout_gen(timeout):
            if check_status():
                log.info('Deployment settled in %s seconds.',
                         (datetime.now() - start).total_seconds())
                return

    def wait_for_messages(self, messages, timeout=300):
        """
        Wait for specific extended status messages to be set via status-set.

        Note that if this is called on an environment that doesn't support
        extended status (pre Juju 1.24), it will raise a
        :class:`~amulet.helpers.UnsupportedError` exception.

        :param dict messages: A mapping of services to an exact message,
            a regular expression, a set of messages or regular expressions,
            or a list of messages or regular expressions.  If a single message
            is given, all units of the service must match.  If a set is given,
            then each message in the set must match at least one unit.  If a
            list is given, then there must be a one-to-one match between the
            messages and the units, though the order doesn't matter.
        :param int timeout: Number of seconds to wait before timing-out.

        Examples::

            # wait for all units to report "ready"
            t.wait_for_messages({'ubuntu': 'ready'})

            # wait for all units to report something like "ready"
            t.wait_for_messages({'ubuntu': re.compile('r..dy')})

            # wait for at least one unit to report "ready"
            t.wait_for_messages({'ubuntu': {'ready'}})

            # wait for all units to report either "ready" or "ok"
            t.wait_for_messages({'ubuntu': re.compile('ready|ok')})

            # wait for at least one unit to report "ready" and at least one
            # unit to report "ok"
            t.wait_for_messages({'ubuntu': {'ready', 'ok'}})

            # wait for one unit to report "ready" and the other to report "ok"
            # (must be exactly two units)
            t.wait_for_messages({'ubuntu': ['ready', 'ok']})
        """
        def get_messages(service, status):
            messages = []
            for unit in status.get(service, {}).values():
                if not unit['workload-status']:
                    raise helpers.UnsupportedError()
                messages.append(unit['workload-status'].get('message', ''))
            return messages

        matcher = StatusMessageMatcher()
        for i in helpers.timeout_gen(timeout):
            status = self.get_status()
            for service, expected in messages.items():
                actual = get_messages(service, status)
                if not matcher.check(expected, actual):
                    break
            else:
                return

    def _sync(self):
        pass


class StatusMessageMatcher(object):
    def check(self, expected, actual):
        if isinstance(expected, (list, tuple)):
            return self.check_list(expected, actual)
        elif isinstance(expected, set):
            return self.check_set(expected, actual)
        else:
            return self.check_messages(expected, actual)

    def check_messages(self, expected, actual):
        """
        Check a single string or regexp against a list of messages.

        All messages must match the string or regexp.
        """
        if not actual:
            return False
        for a in actual:
            if not self.check_message(expected, a):
                return False
        return True

    def check_set(self, expected, actual):
        """
        Check a set of strings or regexps against a list of messages.

        Each expected string or regexp must match at least once.
        """
        if not actual:
            return False
        for e in expected:
            for a in actual:
                if self.check_message(e, a):
                    break  # match, go to next expected
            else:
                return False  # no match for this expected (all must match)
        return True

    def check_list(self, expected, actual):
        """
        Check a list of strings or regexps against a list of messages.

        Each expected string or regexp must match once, and all messages must be matched.
        If an expected string or regexp matches multiple messages, longer matches are
        preferred, to resolve the ambiguity.
        """
        if len(actual) != len(expected):
            return False
        actual = list(actual)  # copy
        for e in expected:
            im = None
            m = 0
            for i, a in enumerate(actual):
                n = self.check_message(e, a)
                if n > m:  # prefer longest matches
                    im = i
                    m = n
            if im is None:
                return False  # no matches for this expected (all must match)
            actual.pop(im)  # remove matched to ensure 1-to-1
        return True

    def check_message(self, expected, actual):
        """
        Check a single string or regexp against a single message.

        Returns the length of the match (0 for no match), to allow for preferring longer matches.
        """
        if hasattr(expected, 'search'):
            m = expected.search(actual)
            return len(m.group()) if m else 0
        elif expected == actual:
            return len(actual)
        else:
            return 0


class ServiceSentry(Sentry):
    pass
