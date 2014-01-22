
import os
import sys
import yaml
import signal
import subprocess

from contextlib import contextmanager

SKIP = 100
PASS = 0
FAIL = 1


class TimeoutError(Exception):
    def __init__(self, value="Timed Out"):
        self.value = value


@contextmanager
def timeout(seconds):
    def signal_handler(signum, frame):
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

    def get_version(self):
        cmd = ['juju', 'version']
        try:
            version = subprocess.check_output(cmd)
        except:
            cmd[1] = '--version'
            version = subprocess.check_output(cmd, stderr=subprocess.STDOUT)

        self.update_version(self.parse_version(version))

    def __str__(self):
        return '.'.join(str(v) for v in [self.major, self.minor, self.patch])


def environments(juju_home="~/.juju/"):
    env_file = os.path.expanduser(os.path.join(juju_home, 'environments.yaml'))
    if not os.path.isfile(env_file):
        raise IOError('%s was not found.' % env_file)

    with open(env_file, 'r') as env_yaml:
        envs = yaml.safe_load(env_yaml.read())

    return envs


def raise_status(code, msg=None):
    if msg:
        print(msg)

    sys.exit(code)


def default_environment(juju_home="~/.juju/"):
    juju_home = os.path.expanduser(juju_home)
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
