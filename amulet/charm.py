import atexit
import os
import shlex
import shutil
import subprocess
import tempfile
import yaml

from .helpers import reify
from .helpers import run_bzr
from charmworldlib.charm import Charm
from path import path
from path import tempdir


class CharmCache(dict):
    def __init__(self, test_charm):
        super(CharmCache, self).__init__()
        self.test_charm = test_charm

    @staticmethod
    def get_charm(charm_path, branch=None, series='precise'):
        if charm_path.startswith('lp:'):
            return LaunchpadCharm(charm_path)
        elif branch and branch.startswith('lp:'):
            return LaunchpadCharm(branch)

        if charm_path.startswith('local:'):
            return LocalCharm(
                os.path.join(
                    os.environ.get('JUJU_REPOSITORY', ''),
                    charm_path[len('local:'):]),
                series
            )

        if branch and branch.endswith('.git'):
            return GitCharm(branch, name=charm_path)

        if os.path.exists(os.path.expanduser(charm_path)):
            return LocalCharm(charm_path, series)

        return Charm(with_series(charm_path, series))

    def __getitem__(self, service):
        return self.fetch(service)

    def fetch(self, service, charm=None, branch=None, series='precise'):
        charm_ = charm
        charm = super(CharmCache, self).get(service, None)
        if charm is not None:
            return charm

        charm = charm_ or service
        charm = os.getcwd() if charm == self.test_charm else charm
        self[service] = self.get_charm(charm,
                                       branch=branch,
                                       series=series)
        return self.get(service)


def with_series(charm_path, series):
    if '/' not in charm_path:
        return '{}/{}'.format(series, charm_path)
    return charm_path


class LocalCharm(object):
    def __init__(self, path, series):
        path = os.path.abspath(os.path.expanduser(path))

        if not os.path.exists(os.path.join(path, 'metadata.yaml')):
            raise Exception('Charm not found')

        if os.path.basename(os.path.dirname(path)) != series:
            path = self._make_temp_copy(path, series)

        self.url = path
        self.subordinate = False
        self.relations = {}
        self.provides = {}
        self.requires = {}
        self.code_source = self.source = None
        self._raw = self._load(os.path.join(path, 'metadata.yaml'))
        self._parse(self._raw)

    def _make_temp_copy(self, path, series):
        d = tempfile.mkdtemp(prefix='charm')
        atexit.register(shutil.rmtree, d)

        series_dir = os.path.join(d, series)
        os.mkdir(series_dir)
        temp_charm_dir = os.path.join(series_dir, os.path.basename(path))

        def ignore(src, names):
            return ['.git', '.bzr']

        shutil.copytree(path, temp_charm_dir, symlinks=True, ignore=ignore)
        return temp_charm_dir

    def _parse(self, metadata):
        rel_keys = ['provides', 'requires']
        for key, val in metadata.items():
            if key in rel_keys:
                self.relations[key] = val

            setattr(self, key, val)

    def _load(self, metadata_path):
        with open(metadata_path) as f:
            data = yaml.safe_load(f.read())

        return data

    def __str__(self):
        return yaml.dump(self._raw)

    def __repr__(self):
        return '<LocalCharm %s>' % self.url


class VCSCharm(object):

    def _parse(self, metadata):
        rel_keys = ['provides', 'requires']
        for key, val in metadata.items():
            if key in rel_keys:
                self.relations[key] = val

            setattr(self, key, val)

    def __str__(self):
        return yaml.dump(self._raw)


class GitCharm(VCSCharm):
    call = staticmethod(subprocess.check_call)

    def __init__(self, fork, name=None):
        self.name = name
        self.url = None
        self.subordinate = False
        self.code_source = self.source = {'location': fork, 'type': 'git'}
        self.relations = {}
        self.provides = {}
        self.requires = {}
        self.branch = self.fork = fork
        self._parse(self._raw)

    @reify
    def _raw(self):
        with tempdir() as td:
            cmd = "git clone -n --depth=1 {} {}"\
                .format(self.fork, self.name)

            with path(td):
                self.call(shlex.split(cmd))

            cmd = "git checkout HEAD metadata.yaml"
            with td / self.name:
                self.call(shlex.split(cmd))

            md = td / self.name / 'metadata.yaml'
            txt = md.text()
        return yaml.safe_load(txt)

    def __repr__(self):
        return '<GitCharm %s>' % self.code_source['location']


class LaunchpadCharm(VCSCharm):
    def __init__(self, branch):
        self.url = None
        self.subordinate = False
        self.code_source = self.source = {'location': branch, 'type': 'bzr'}
        self.relations = {}
        self.provides = {}
        self.requires = {}
        self._branch = branch
        self._parse(self._raw)

    @reify
    def _raw(self):
        metadata_path = path(self._branch) / 'metadata.yaml'
        mdata = run_bzr(['cat', metadata_path], None)
        return yaml.safe_load(mdata)

    def __repr__(self):
        return '<LaunchpadCharm %s>' % self.code_source['location']
