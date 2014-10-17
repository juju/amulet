import amulet
import unittest


class TestDeployment(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.deployment = amulet.Deployment()

        cls.deployment.add('pictor')
        cls.deployment.add('haproxy')
        cls.deployment.relate('pictor:website', 'haproxy:reverseproxy')

        try:
            cls.deployment.setup(timeout=900)
            cls.deployment.sentry.wait()
        except amulet.helpers.TimeoutError:
            amulet.raise_status(
                amulet.SKIP, msg="Environment wasn't stood up in time")
        except:
            raise

        # For testing new relation code, make a real relation between
        # services, bypassing relation-sentry
        #import subprocess
        #subprocess.call('juju add-relation pictor haproxy'.split())

        cls.pictor = cls.deployment.sentry['pictor/0']
        cls.haproxy = cls.deployment.sentry['haproxy/0']
        cls.pictor.run_new(
            'mkdir -p /tmp/amulet-test/test-dir;'
            'echo contents > /tmp/amulet-test/test-file;'
        )

    def test_info(self):
        self.assertTrue('public-address' in self.pictor.info)
        self.assertEqual('pictor', self.pictor.info['service'])
        self.assertEqual('0', self.pictor.info['unit'])

    def test_file_stat(self):
        path = '/tmp/amulet-test/test-file'
        self.assertEqual(
            self.pictor.file_stat(path),
            self.pictor.file_stat_new(path),
        )
        stat = self.pictor.file_stat_new(path)
        self.assertTrue(stat.pop('mtime'))
        self.assertEqual(
            stat, {
                'size': 9,
                'uid': 0,
                'gid': 0,
                'mode': '0100644',
            },
        )

    def test_file_contents(self):
        path = '/tmp/amulet-test/test-file'
        self.assertEqual(
            self.pictor.file_contents(path),
            self.pictor.file_contents_new(path),
        )
        self.assertEqual(
            self.pictor.file_contents_new(path),
            'contents\n',
        )

    def test_directory_stat(self):
        path = '/tmp/amulet-test'
        self.assertEqual(
            self.pictor.directory_stat(path),
            self.pictor.directory_stat_new(path),
        )
        stat = self.pictor.directory_stat_new(path)
        self.assertTrue(stat.pop('mtime'))
        self.assertEqual(
            stat, {
                'size': 4096,
                'uid': 0,
                'gid': 0,
                'mode': '040755',
            },
        )

    def test_directory_listing(self):
        path = '/tmp/amulet-test'
        self.assertEqual(
            self.pictor.directory_listing(path),
            self.pictor.directory_listing_new(path),
        )
        self.assertEqual(
            self.pictor.directory_listing_new(path), {
                'files': ['test-file'],
                'directories': ['test-dir'],
            },
        )

    def test_relation(self):
        pictor_info = self.pictor.relation_new(
            'website', 'haproxy:reverseproxy')
        for key in ['hostname', 'port', 'private-address']:
            self.assertTrue(key in pictor_info)

        self.assertEqual(
            self.pictor.relation('website', 'haproxy:reverseproxy'),
            pictor_info,
        )
        self.assertEqual(
            self.haproxy.relation('reverseproxy', 'pictor:website'),
            self.haproxy.relation_new('reverseproxy', 'pictor:website'),
        )

    def test_run(self):
        self.assertEqual(
            self.pictor.run('echo hello'),
            self.pictor.run_new('echo hello'),
        )
        self.assertEqual(
            self.pictor.run_new('echo hello'),
            ('hello', 0),
        )

        # Now you can use self.deployment.sentry.unit[UNIT] to address each of
        # the units and perform more in-depth steps.  You can also reference
        # the first unit as self.unit.
        # There are three test statuses that can be triggered with
        # amulet.raise_status():
        #   - amulet.PASS
        #   - amulet.FAIL
        #   - amulet.SKIP
        # Each unit has the following methods:
        #   - .info - An array of the information of that unit from Juju
        #   - .file(PATH) - Get the details of a file on that unit
        #   - .file_contents(PATH) - Get plain text output of PATH file from that unit
        #   - .directory(PATH) - Get details of directory
        #   - .directory_contents(PATH) - List files and folders in PATH on that unit
        #   - .relation(relation, service:rel) - Get relation data from return service
        #          add tests here to confirm service is up and working properly
        # For example, to confirm that it has a functioning HTTP server:
        #     page = requests.get('http://{}'.format(self.unit.info['public-address']))
        #     page.raise_for_status()
        # More information on writing Amulet tests can be found at:
        #     https://juju.ubuntu.com/docs/tools-amulet.html


if __name__ == '__main__':
    unittest.main()
