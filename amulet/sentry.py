import gc
import glob
import json
import logging
import os
import subprocess
from datetime import datetime

import pkg_resources

from . import actions
from . import waiter
from . import helpers

JUJU_VERSION = helpers.JUJU_VERSION


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
    """A proxy to a deployed unit, through which the unit can be
    manipulated.

    Provides methods for running commands on the unit and fetching
    relation data from units to which this unit is related.

    :ivar dict info: A dictionary containing 'unit_name' (in the form
        'wordpress/0'), 'service' (name), 'unit' (unit number as string),
        'machine' (machine number as string), 'public-address', and
        'agent-version'.

    """
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

    def list_actions(self):
        """Return list of actions defined for this unit.

        :return: List of actions, as json.

        """
        return actions.list_actions(self.info['service'])
    action_defined = list_actions

    def run_action(self, action, action_args=None):
        """Run an action on this unit and return the result UUID.

        :param action: Name of action to run.
        :param action_args: Dictionary of action parameters.
        :return str: The action UUID.

        """
        return actions.run_action(
            self.info['unit_name'], action, action_args=action_args)
    action_do = run_action

    def upload_scripts(self):
        source = pkg_resources.resource_filename(
            'amulet', os.path.join('unit-scripts', 'amulet'))
        dest = '/tmp/amulet'
        mkdir_cmd = 'mkdir -p -m a=rwx {}'.format(dest)
        output, code = self.ssh(mkdir_cmd, raise_on_failure=False)
        if code != 0:
            # try one more time
            self.ssh(mkdir_cmd, raise_on_failure=True)

        # copy one at a time b/c `juju scp -r` doesn't work (currently)
        for f in glob.glob(os.path.join(source, '*.py')):
            cmd = "juju scp {} {}:{}".format(
                os.path.join(source, f),
                self.info['unit_name'], dest)
            subprocess.check_call(cmd.split())

    def _fs_data(self, path):
        return self._run_unit_script("filesystem_data.py {}".format(path))

    def file_stat(self, filename):
        """Run :func:`os.stat` against ``filename`` on the unit.

        :param str filename: Path of file to stat on the remote unit.
        :return: Dictionary containing ``mtime``, ``size``, ``uid``,
            ``gid``, and ``mode`` of ``filename``.

        """
        return self._fs_data(filename)

    def file_contents(self, filename):
        """Get the contents of ``filename`` on the remote unit.

        :param str filename: Path of file to stat on the remote unit.
        :raises: IOError if the call fails.
        :return: File contents as string.

        """
        output, return_code = self._run('cat {}'.format(filename))
        if return_code == 0:
            return output
        else:
            raise IOError(output)

    def directory_stat(self, path):
        """Run :func:`os.stat` against ``path`` on the unit.

        :param str path: Path of directory to stat on the remote unit.
        :return: Dictionary containing ``mtime``, ``size``, ``uid``,
            ``gid``, and ``mode`` of ``path``.

        """
        return self._fs_data(path)

    def directory_listing(self, path):
        """Get the contents of the directory at ``path`` on the remote unit.

        :param str path: Path of directory on the remote unit.
        :return: Dictionary containing 'files' and 'directories', both lists.

        This method does the equivalent of the following, on the remote unit::

            contents = {'files': [], 'directories': []}
            for fd in os.listdir(path):
                if os.path.isfile('{}/{}'.format(path, fd)):
                    contents['files'].append(fd)
                else:
                    contents['directories'].append(fd)
            return contents

        """
        return self._run_unit_script("directory_listing.py {}".format(path))

    def run(self, command):
        """Run an arbitrary command (as root) on the remote unit.

        Uses ``juju run`` to execute the command, which means the command
        will be queued to run after already-queued hooks. To avoid this
        behavior and instead execute the command immediately, see the
        :meth:`ssh` method.

        :param str command: The command to run.
        :return: A 2-tuple containing the output of the command and the exit
            code of the command.

        A default timeout of 5 minutes is imposed on the command. To change
        this timeout, see the :meth:`_run` method.

        """
        output, code = self._run(command)
        return output.strip(), code

    def _run(self, command, unit=None, timeout=300):
        """Run an arbitrary command (as root) on the remote unit.

        Uses ``juju run`` to execute the command, which means the command
        will be queued to run after already-queued hooks. To avoid this
        behavior and instead execute the command immediately, see the
        :meth:`ssh` method.

        :param str command: The command to run.
        :param str unit: Unit on which to run the command, in the form
            'wordpress/0'. If None, defaults to the unit for this
            :class:`UnitSentry`.
        :param int timeout: Seconds to wait before timing out.
        :return: A 2-tuple containing the output of the command and the exit
            code of the command.

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
        """Run an arbitrary command (as the ubuntu user) against a remote
        unit, using `juju ssh`.

        Using `juju ssh` bypasses the Juju execution queue, so it will not
        be blocked by running hooks.  Note, however, that the command is run
        as the ubuntu user instead of root.

        :param str command: The command to run.
        :param str unit: Unit on which to run the command, in the form
            'wordpress/0'. If None, defaults to the unit for this
            :class:`UnitSentry`.
        :param bool raise_on_failure: If True, raises
            :class:`subprocess.CalledProcessError` if the command fails.
        :return: A 2-tuple containing the output of the command and the exit
            code of the command.

        """
        unit = unit or self.info['unit_name']
        cmd = ['juju', 'ssh', unit, '-v', command]
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = p.communicate()
        output = stdout if p.returncode == 0 else stderr
        if p.returncode != 0:
            print(output)
            if raise_on_failure:
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
        """Get relation data from the remote unit to which we are related,
        denoted by ``to_rel``.

        :param str from_rel: The local side of the relation, e.g. 'website'.
        :param str to_rel: The remote side of the relation,
            e.g. 'haproxy:reverseproxy'.
        :return: Dictionary containing the results of `relation-get`, run
            on the unit on the remote side of the relation.

        """
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


class Talisman(object):
    """A dict-like object containing a collection of :class:`UnitSentry`
    objects, one for each unit in the deployment.

    Also provides assorted 'wait\_' methods which will block until the
    deployment reaches a certain state.

    See :meth:`__getitem__` for details on retrieving the :class:`UnitSentry`
    objects.

    :note: Under ordinary circumstances this class should not be instantiated
        manually. It should instead be access through the
        :attr:`~amulet.deployer.Deployment.sentry` attribute on an
        :class:`amulet.deployer.Deployment` instance.

    """

    def __init__(self, services, rel_sentry='relation-sentry',
                 juju_env=None, timeout=300):
        self.service_names = services
        self.unit = {}
        self.service = {}

        self.juju_env = juju_env or helpers.default_environment()

        # Save the juju status so we can inspect it later if we don't
        # end up with what we expect in our dictionary of sentries.
        self.status = self.wait_for_status(self.juju_env, services, timeout)

        for service in services:
            if service not in self.status['services']:
                continue  # Raise something?

            service_status = self.status['services'][service]

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

        Raises a KeyError if the unit does not exist.

        Returns an empty list if the service does not exist or has
        no units.

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
        if '/' in service:
            unit_name = service
            return self.unit[unit_name]
        else:
            return [unit_sentry
                    for unit_name, unit_sentry in sorted(self.unit.items())
                    if service == unit_name.split('/', 1)[0]]

    def get_status(self, juju_env=None):
        status = waiter.status(juju_env or self.juju_env)
        machine_states = {}
        normalized = {}

        def machine_state(machine_dict):
            if JUJU_VERSION.major == 1:
                return machine_dict.get('agent-state')
            return machine_dict.get('juju-status', {}).get('current')

        def agent_status(unit_dict):
            key = 'agent-status' if JUJU_VERSION.major == 1 else 'juju-status'
            return unit_dict.get(key, {})

        for number, machine in status['machines'].items():
            machine_states[number] = machine_state(machine)
            for container_name, container in machine.get('containers', {}).items():
                machine_states[container_name] = machine_state(container)

        for service_name, service in status['services'].items():
            if 'units' not in service and 'relations' not in service:
                # ignore unrelated subordinates; they will never become ready
                continue
            normalized.setdefault(service_name, {})
            for unit_name, unit in service.get('units', {}).items():
                normalized[service_name][unit_name] = {
                    'machine-state': machine_states.get(unit.get('machine')),
                    'public-address': unit.get('public-address'),
                    'workload-status': unit.get('workload-status', {}),
                    'agent-status': agent_status(unit),
                    'agent-state': unit.get('agent-state'),
                    'agent-state-info': unit.get('agent-state-info'),
                }
                for sub_name, sub in unit.get('subordinates', {}).items():
                    sub_service = sub_name.split('/')[0]
                    normalized.setdefault(sub_service, {})
                    normalized[sub_service][sub_name] = {
                        'machine-state': machine_states.get(unit.get('machine')),
                        'public-address': sub.get('public-address'),
                        'workload-status': sub.get('workload-status', {}),
                        'agent-status': agent_status(sub),
                        'agent-state': sub.get('agent-state'),
                        'agent-state-info': sub.get('agent-state-info'),
                    }
        return normalized

    def wait_for_status(self, juju_env, services, timeout=300):
        """Return environment status, but only after all units have a
        public-address assigned and are in a 'started' state.

        This method is called automatically by :meth:`__init__`, meaning that
        initialization of this :class:`Talisman` object will not complete
        until this method returns. Under ordinary circumstances you should
        not need to call this method manually.

        Raises if a unit reaches error state, or if public-address not
        available for all units before timeout expires.

        :param str juju_env: Name of the juju environment.
        :param dict services: Dictionary of services in the environment.
        :param int timeout: Time to wait before timing out. If environment
            variable AMULET_WAIT_TIMEOUT is set, it overrides this value.
        :return: Dictionary of juju enviroment status.

        """
        timeout = int(os.environ.get('AMULET_WAIT_TIMEOUT') or timeout)

        def check_status(status, juju_env, services):
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
                    # Some substrates (like Amazon) will return a
                    # public-address while the machine is still allocating, so
                    # it's necessary to also check the agent-state to see if
                    # the unit is ready.
                    if unit['agent-state'] not in (None, 'started'):
                        return False
            return True

        for i in helpers.timeout_gen(timeout):
            status = self.get_status(juju_env)
            if check_status(status, juju_env, services):
                return waiter.status(juju_env)
            del status
            gc.collect()

    def wait(self, timeout=300):
        """Wait for all units to finish running hooks.

        :param int timeout: Number of seconds to wait before timing-out.
            If environment variable AMULET_WAIT_TIMEOUT is set, it overrides
            this value.
        :raises: :class:`amulet.TimeoutError` if the timeout is exceeded.

        """
        timeout = int(os.environ.get('AMULET_WAIT_TIMEOUT') or timeout)

        def check_status(status):
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
            status = self.get_status()
            if check_status(status):
                log.info('Deployment settled in %s seconds.',
                         (datetime.now() - start).total_seconds())
                return
            del status
            gc.collect()

    def wait_for_messages(self, messages, timeout=300):
        """Wait for specific extended status messages to be set via status-set.

        Note that if this is called on an environment that doesn't support
        extended status (pre Juju 1.24), it will raise an
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
            del status
            gc.collect()

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

        Each expected string or regexp must match once, and all messages must
        be matched.  If an expected string or regexp matches multiple messages,
        longer matches are preferred, to resolve the ambiguity.

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

        Returns the length of the match (0 for no match), to allow for
        preferring longer matches.

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
