from __future__ import print_function
import functools
import os
import sys
import yaml
import signal
import subprocess
import errno
from datetime import datetime

from contextlib import contextmanager

SKIP = 100
PASS = 0
FAIL = 1


class TimeoutError(Exception):
    def __init__(self, value="Timed Out"):
        self.value = value


class UnsupportedError(Exception):
    pass


def _as_text(bytestring):
    """Naive conversion of subprocess output to Python string"""
    return bytestring.decode("utf-8", "replace")


def setup_bzr(charm_dir):
    try:
        run_bzr(['whoami'], charm_dir)
    except IOError:
        run_bzr(['whoami', 'amulet@dummy-user.tld'], charm_dir)

    run_bzr(["init"], charm_dir)
    # Set the maximum file size to 0 to avoid skipping any files in the
    # charm.
    run_bzr(['config', 'add.maximum_file_size=0'], charm_dir)


def run_bzr(args, working_dir, env=None):
    """Run a Bazaar command in a subprocess"""
    try:
        p = subprocess.Popen(["bzr"] + args, cwd=working_dir, env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise
        raise OSError("bzr not found, do you have Bazaar installed?")
    out, err = p.communicate()
    if p.returncode:
        raise IOError("bzr command failed {!r}:\n"
                      "{}".format(args, _as_text(err)))
    return _as_text(out)


def juju(args, env=None):
    try:
        p = subprocess.Popen(['juju'] + args, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise
        raise OSError("juju not found, do you have Juju installed?")
    out, err = p.communicate()
    if p.returncode:
        raise IOError("juju command failed {!r}:\n"
                      "{}".format(args, _as_text(err)))
    return _as_text(out) if out else None


def timeout_gen(seconds):
    """
    Return a counting generator that raises a :class:`TimeoutError` after
    a number of seconds.

    Note, this is non-preemptive; that is, it will only check for timeout
    between iterations.  This means that it is guaranteed to not timeout
    in the middle of doing its work / checking, which makes it more
    deterministic and easier to debug, but also means that you must ensure
    that the block does not contain an infinite loop or blocking system
    call that needs to be preempted.  If you need a preemptive timeout, see
    :func:`timeout`.

    :param float seconds: Number of seconds after which to timeout.

    Examples::

        for i in timeout(30):
            if i >= 40:
                break  # will timeout first
            sleep(10)

        # wrong!
        for i in timeout(30):
            sleep(60)  # will not preempt! this will take 60s
    """
    start = datetime.now()
    i = 0
    while True:
        yield i
        if (datetime.now() - start).total_seconds() > seconds:
            sys.stderr.write('Timeout occurred, printing juju status...')
            sys.stderr.write(juju(['status']))
            raise TimeoutError()
        i += 1


@contextmanager
def timeout(seconds):
    def signal_handler(signum, frame):
        sys.stderr.write('Timeout occurred, printing juju status...')
        sys.stderr.write(juju(['status']))
        raise TimeoutError()
    signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)


class JujuVersion(object):
    def __init__(self, major=0, minor=0, patch=0, get_version=True):
        self.mapping = ['major', 'minor', 'patch']
        self.major = major
        self.minor = minor
        self.patch = patch

        if get_version:
            self.get_version()

    def parse_version(self, version_str):
        version = version_str.split()
        if len(version) > 1:
            version_str = str(version[1])
        else:
            version_str = str(version[0])

        return version_str.split('-')[0].split('.')

    def update_version(self, version_list):
        for i, ver in enumerate(version_list):
            try:
                setattr(self, self.mapping[i], int(ver))
            except:
                break  # List out of range? Versions not semantic? Too bad
        while i < (len(self.mapping) - 1):
            i += 1
            setattr(self, self.mapping[i], None)

    def get_version(self):
        try:
            version = juju(['version'])
        except:
            version = juju(['--version'])

        self.update_version(self.parse_version(version))

    def __str__(self):
        return '.'.join(str(v) for v in [self.major, self.minor, self.patch]
                        if v is not None)


def environments(juju_home=None):
    juju_home = os.path.expanduser(
        juju_home or os.environ.get('JUJU_HOME') or '~/.juju/')
    env_file = os.path.join(juju_home, 'environments.yaml')
    if not os.path.isfile(env_file):
        raise IOError('%s was not found.' % env_file)

    with open(env_file, 'r') as env_yaml:
        envs = yaml.safe_load(env_yaml.read())

    return envs


def raise_status(code, msg=None):
    if msg:
        print(msg)

    sys.exit(code)


def default_environment(juju_home=None):
    juju_home = os.path.expanduser(
        juju_home or os.environ.get('JUJU_HOME') or '~/.juju/')
    envs = environments(juju_home)

    if 'JUJU_ENV' in os.environ:
        return os.environ['JUJU_ENV']

    if os.path.exists(os.path.join(juju_home, 'current-environment')):
        cur_env = None
        with open(os.path.join(juju_home, 'current-environment')) as f:
            cur_env = f.read().strip()

        if cur_env in envs['environments']:
            return cur_env

    if 'default' in envs:
        return envs['default']
    else:
        if len(envs['environments']) != 1:
            raise ValueError('No default environment specified.')

        return next(iter(envs['environments'].keys()))


class reify(object):
    def __init__(self, func):
        self.func = func
        try:
            functools.update_wrapper(self, func)
        except:
            pass

    def __get__(self, inst, obtype=None):
        if inst is None:
            return self

        out = self.func(inst)
        setattr(inst, self.func.__name__, out)
        return out


@contextmanager
def fail_if_timeout(seconds):
    try:
        yield
    except TimeoutError:
        message = 'Unable to set up environment in %d seconds.' % seconds
        raise_status(FAIL, msg=message)
    except:
        raise
