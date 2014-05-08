import sys
import base64
import hashlib
import json
import os
import shutil
import tempfile

from mock import patch
from unittest import TestCase

server_location = os.path.join(
    os.path.dirname(__file__), '../', 'amulet', 'charms', 'sentry', 'src')
sys.path.insert(0, server_location)

os.chdir(server_location)

import cherrypy

import server
import json_rpc
from modules import docs
from modules import filesystem
from modules import juju
from modules import relations
from modules import run


class TestInstance(TestCase):
    def setUp(self):
        super(TestInstance, self).setUp()

        users = {'admin': hashlib.sha512(u'admin'.encode()).hexdigest()}
        self.tempdir = tempfile.mkdtemp()
        os.chdir(self.tempdir)
        with open('users.json', 'w') as f:
            json.dump(users, f)

    def tearDown(self):
        shutil.rmtree(self.tempdir)
        os.chdir(server_location)

    def test_check_credentials(self):
        inst = server.Instance()

        self.assertTrue(inst._check_credentials(u'admin', u'admin'))
        self.assertFalse(inst._check_credentials(u'admin', u'foo'))

    def test_validate(self):
        inst = server.Instance()

        basic_auth_header = u'Basic {}'.format(
            base64.b64encode(b'admin:admin').decode())
        self.assertFalse(inst._validate("Digest"))
        self.assertTrue(inst._validate(basic_auth_header))


class TestDocs(TestCase):
    def test_index(self):
        mod = docs.Module()

        self.assertEqual(mod.index().read(), u"You shouldn't be here.\n")


class TestFilesystem(TestCase):
    @patch('modules.filesystem.cherrypy.request')
    def test_file_not_GET(self, request):
        request.method = 'POST'

        mod = filesystem.Module()

        with self.assertRaises(cherrypy.HTTPError) as e:
            mod.file()
            self.assertEqual(e.status, 405)

    @patch('modules.filesystem.cherrypy.request')
    def test_file_no_name(self, request):
        request.method = 'GET'

        mod = filesystem.Module()

        with self.assertRaises(cherrypy.HTTPError) as e:
            mod.file()
            self.assertEqual(e.status, 400)

    @patch('modules.filesystem.cherrypy.request')
    def test_file_bad_action(self, request):
        request.method = 'GET'

        mod = filesystem.Module()

        with self.assertRaises(cherrypy.HTTPError) as e:
            mod.file(action='list')
            self.assertEqual(e.status, 400)

    @patch('modules.filesystem.cherrypy.request')
    def test_file_no_such_file(self, request):
        request.method = 'GET'

        mod = filesystem.Module()

        with self.assertRaises(cherrypy.HTTPError) as e:
            mod.file(name='/tmp/no-such-file')
            self.assertEqual(e.status, 404)

    @patch('modules.filesystem.cherrypy.request')
    def test_file_stat(self, request):
        request.method = 'GET'

        mod = filesystem.Module()

        with tempfile.NamedTemporaryFile() as f:
            r = json.loads(mod.file(name=f.name).decode())
            stat = os.stat(f.name)
            self.assertEqual(r['mtime'], stat.st_mtime)
            self.assertEqual(r['size'], stat.st_size)
            self.assertEqual(r['uid'], stat.st_uid)
            self.assertEqual(r['gid'], stat.st_gid)
            self.assertEqual(r['mode'], oct(stat.st_mode))

    @patch('modules.filesystem.cherrypy.request')
    def test_file_contents(self, request):
        request.method = 'GET'

        mod = filesystem.Module()

        with tempfile.NamedTemporaryFile() as f:
            f.write(b'Test')
            f.flush()
            self.assertEqual(b'Test', mod.file(action='contents', name=f.name))

    @patch('modules.filesystem.cherrypy.request')
    def test_directory_not_GET(self, request):
        request.method = 'POST'

        mod = filesystem.Module()

        with self.assertRaises(cherrypy.HTTPError) as e:
            mod.directory()
            self.assertEqual(e.status, 405)

    @patch('modules.filesystem.cherrypy.request')
    def test_directory_no_name(self, request):
        request.method = 'GET'

        mod = filesystem.Module()

        with self.assertRaises(cherrypy.HTTPError) as e:
            mod.directory()
            self.assertEqual(e.status, 400)

    @patch('modules.filesystem.cherrypy.request')
    def test_directory_bad_action(self, request):
        request.method = 'GET'

        mod = filesystem.Module()

        with self.assertRaises(cherrypy.HTTPError) as e:
            mod.directory(action='list')
            self.assertEqual(e.status, 400)

    @patch('modules.filesystem.cherrypy.request')
    def test_directory_no_such_directory(self, request):
        request.method = 'GET'

        mod = filesystem.Module()

        with self.assertRaises(cherrypy.HTTPError) as e:
            mod.directory(name='/tmp/no-such-directory')
            self.assertEqual(e.status, 404)

    @patch('modules.filesystem.cherrypy.request')
    def test_directory_stat(self, request):
        request.method = 'GET'

        mod = filesystem.Module()

        tempdir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(tempdir))

        r = json.loads(mod.directory(name=tempdir).decode())
        stat = os.stat(tempdir)
        self.assertEqual(r['mtime'], stat.st_mtime)
        self.assertEqual(r['size'], stat.st_size)
        self.assertEqual(r['uid'], stat.st_uid)
        self.assertEqual(r['gid'], stat.st_gid)
        self.assertEqual(r['mode'], oct(stat.st_mode))

    @patch('modules.filesystem.cherrypy.request')
    def test_directory_contents(self, request):
        request.method = 'GET'

        mod = filesystem.Module()

        tempdir = tempfile.mkdtemp()
        tempfile.mkdtemp(prefix='mydir', dir=tempdir)
        tempfile.mkstemp(prefix='myfile', dir=tempdir)
        self.addCleanup(lambda: shutil.rmtree(tempdir))

        contents = json.loads(
            mod.directory(action='contents', name=tempdir).decode())
        self.assertEqual(len(contents['directories']), 1)
        self.assertEqual(len(contents['files']), 1)
        self.assertTrue(contents['directories'][0].startswith('mydir'))
        self.assertTrue(contents['files'][0].startswith('myfile'))


class TestJuju(TestCase):
    def test_juju_active_hook(self):
        tempdir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(tempdir))

        with patch('modules.juju.PROC_DIR', tempdir):
            os.mkdir(os.path.join(tempdir, '123'))
            with open(os.path.join(tempdir, '123', 'cmdline'), 'w') as f:
                f.write(u'/var/lib/juju/agents/charm/hooks/install')
                f.flush()

            mod = juju.Module()
            r = json.loads(mod.juju().decode())
            self.assertEqual(r['hook'], u'install')

    def test_juju_no_active_hook(self):
        tempdir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(tempdir))

        with patch('modules.juju.PROC_DIR', tempdir):
            os.mkdir(os.path.join(tempdir, '1'))
            with open(os.path.join(tempdir, '1', 'cmdline'), 'w') as f:
                f.write(u'/sbin/init')
                f.flush()

            mod = juju.Module()
            r = json.loads(mod.juju().decode())
            self.assertEqual(r, {})


class TestRelations(TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        patcher = patch('modules.relations.RELATIONS_DIR', self.tempdir)
        patcher.start()
        self.addCleanup(lambda: shutil.rmtree(self.tempdir))
        self.addCleanup(patcher.stop)

    @patch('modules.relations.cherrypy.request')
    def test_relations_not_GET(self, request):
        request.method = 'POST'

        mod = relations.Module()

        with self.assertRaises(cherrypy.HTTPError) as e:
            mod.relations()
            self.assertEqual(e.status, 405)

    @patch('modules.relations.cherrypy.request')
    def test_relations_no_dir(self, request):
        request.method = 'GET'

        mod = relations.Module()

        with patch('modules.relations.RELATIONS_DIR', '/tmp/no-such-dir'):
            self.assertEqual({}, json.loads(mod.relations().decode()))

    @patch('modules.relations.cherrypy.request')
    def test_relations(self, request):
        request.method = 'GET'

        mod = relations.Module()

        os.mkdir(os.path.join(self.tempdir, 'myrelation'))
        os.mkdir(os.path.join(self.tempdir, 'myrelation', '1'))

        expected = {'myrelation': ['1']}
        self.assertEqual(expected, json.loads(mod.relations().decode()))

    @patch('modules.relations.cherrypy.request')
    def test_relation_not_GET(self, request):
        request.method = 'POST'

        mod = relations.Module()

        with self.assertRaises(cherrypy.HTTPError) as e:
            mod.relation()
            self.assertEqual(e.status, 405)

    @patch('modules.relations.cherrypy.request')
    def test_relation_no_relation(self, request):
        request.method = 'GET'

        mod = relations.Module()

        with self.assertRaises(cherrypy.HTTPError) as e:
            mod.relation()
            self.assertEqual(e.status, 400)

    @patch('modules.relations.cherrypy.request')
    def test_relation_no_dir(self, request):
        request.method = 'GET'

        mod = relations.Module()

        with self.assertRaises(cherrypy.HTTPError) as e:
            mod.relation(relation='myrelation')
            self.assertEqual(e.status, 404)

    @patch('modules.relations.cherrypy.request')
    def test_relation_no_unit(self, request):
        request.method = 'GET'

        mod = relations.Module()

        os.mkdir(os.path.join(self.tempdir, 'myrelation'))
        os.mkdir(os.path.join(self.tempdir, 'myrelation', '1'))
        with open(os.path.join(
                self.tempdir, 'myrelation', '1', 'data'), 'w') as f:
            json.dump({'unit_data_key': 'unit_data_value'}, f)

        expected = {'1': {'unit_data_key': 'unit_data_value'}}
        self.assertEqual(
            expected, json.loads(mod.relation(relation='myrelation').decode()))

    @patch('modules.relations.cherrypy.request')
    def test_relation_no_unit_data_file(self, request):
        request.method = 'GET'

        mod = relations.Module()

        os.mkdir(os.path.join(self.tempdir, 'myrelation'))
        os.mkdir(os.path.join(self.tempdir, 'myrelation', '1'))

        with self.assertRaises(cherrypy.HTTPError) as e:
            mod.relation(relation='myrelation', unit='1')
            self.assertEqual(e.status, 404)

    @patch('modules.relations.cherrypy.request')
    def test_relation_with_unit(self, request):
        request.method = 'GET'

        mod = relations.Module()

        os.mkdir(os.path.join(self.tempdir, 'myrelation'))
        os.mkdir(os.path.join(self.tempdir, 'myrelation', '1'))
        with open(os.path.join(
                self.tempdir, 'myrelation', '1', 'data'), 'w') as f:
            json.dump({'unit_data_key': 'unit_data_value'}, f)

        expected = {'unit_data_key': 'unit_data_value'}
        self.assertEqual(
            expected,
            json.loads(mod.relation(relation='myrelation', unit='1').decode()))

    def test_list_units(self):
        mod = relations.Module()

        os.mkdir(os.path.join(self.tempdir, 'myrelation'))
        os.mkdir(os.path.join(self.tempdir, 'myrelation', '1'))

        self.assertEqual(['1'], mod.list_units('myrelation'))


class TestRun(TestCase):
    @patch('modules.run.cherrypy.request')
    def test_run_invalid_http_method(self, request):
        request.method = 'GET'

        mod = run.Module()

        with self.assertRaises(cherrypy.HTTPError) as e:
            mod.run()
            self.assertEqual(e.status, 405)

    @patch('modules.run.cherrypy.request')
    def test_run_success(self, request):
        request.method = 'POST'
        request.body.read.return_value = b'echo hello'

        mod = run.Module()

        expected = {'code': 0, 'output': 'hello'}
        self.assertEqual(expected, json.loads(mod.run().decode()))

    @patch('modules.run.cherrypy.response')
    @patch('modules.run.cherrypy.request')
    def test_run_error(self, request, response):
        request.method = 'POST'
        request.body.read.return_value = b'false'

        mod = run.Module()

        expected = {'code': 1, 'output': ''}
        self.assertEqual(expected, json.loads(mod.run().decode()))
        self.assertEqual(500, response.status)


class TestJsonRpc(TestCase):
    def setUp(self):
        class Fixture(object):
            def _validate(self, auth):
                return auth == 'true'

            def test_func(self, *args, **kwargs):
                return dict(args=list(args), kwargs=kwargs)
        self.fixture = Fixture
        self.expected = {'args': [1], 'kwargs': {'b': 2}}

    @patch('json_rpc.cherrypy.request')
    def test_secure_auth_succeeds(self, request):
        request.headers = {'Authorization': 'true'}

        self.fixture.test_func = json_rpc.secure(self.fixture.test_func)
        self.assertEqual(self.expected, self.fixture().test_func(1, b=2))

    @patch('json_rpc.cherrypy.response')
    @patch('json_rpc.cherrypy.request')
    def test_secure_auth_fails(self, request, response):
        request.headers = {'Authorization': 'false'}

        self.fixture.test_func = json_rpc.secure(self.fixture.test_func)
        with self.assertRaises(cherrypy.HTTPError) as e:
            self.fixture().test_func(1, b=2)
            self.assertEqual(e.status, 401)
            self.assertEqual(e.msg, 'Authorization Required')
            self.assertEqual(
                response.headers['WWW-Authenticated'],
                'Basic realm="Secure Area"')

    @patch('json_rpc.cherrypy.response')
    def test_jsonify(self, response):
        response.headers = {}
        self.fixture.test_func = json_rpc.jsonify(self.fixture.test_func)

        self.assertEqual(
            self.expected,
            json.loads(self.fixture().test_func(1, b=2).decode()))
        self.assertEqual(response.headers['Content-Type'], 'application/json')

    @patch('json_rpc.cherrypy.response')
    def test_dont_jsonify(self, response):
        response.headers = {}
        self.fixture.test_func = lambda self: 'test'
        self.fixture.test_func = json_rpc.dont_jsonify(self.fixture.test_func)

        self.assertEqual(b'test', self.fixture().test_func())
        self.assertEqual(response.headers['Content-Type'], 'application/json')
