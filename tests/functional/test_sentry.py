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

        cls.pictor = cls.deployment.sentry['pictor/0']
        cls.haproxy = cls.deployment.sentry['haproxy/0']
        cls.pictor.run(
            'mkdir -p /tmp/amulet-test/test-dir;'
            'echo contents > /tmp/amulet-test/test-file;'
        )

    def test_info(self):
        self.assertTrue('public-address' in self.pictor.info)
        self.assertEqual('pictor', self.pictor.info['service'])
        self.assertEqual('0', self.pictor.info['unit'])
        self.assertEqual('pictor/0', self.pictor.info['unit_name'])

    def test_file_stat(self):
        path = '/tmp/amulet-test/test-file'
        stat = self.pictor.file_stat(path)
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
            'contents\n',
        )

    def test_directory_stat(self):
        path = '/tmp/amulet-test'
        stat = self.pictor.directory_stat(path)
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
            self.pictor.directory_listing(path), {
                'files': ['test-file'],
                'directories': ['test-dir'],
            },
        )

    def test_relation(self):
        pictor_info = self.pictor.relation(
            'website', 'haproxy:reverseproxy')
        for key in ['hostname', 'port', 'private-address']:
            self.assertTrue(key in pictor_info)

        haproxy_info = self.haproxy.relation(
            'reverseproxy', 'pictor:website')
        self.assertEqual(list(haproxy_info.keys()), ['private-address'])

    def test_run(self):
        self.assertEqual(
            self.pictor.run('echo hello'),
            ('hello', 0),
        )


if __name__ == '__main__':
    unittest.main()
