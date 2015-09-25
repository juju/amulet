import amulet
import unittest


class TestDeployment(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.deployment = amulet.Deployment(series='precise')

        cls.deployment.add('nagios')
        cls.deployment.add('haproxy')
        cls.deployment.add('rsyslog-forwarder')
        cls.deployment.relate('nagios:website', 'haproxy:reverseproxy')
        cls.deployment.relate('nagios:juju-info', 'rsyslog-forwarder:juju-info')

        try:
            cls.deployment.setup(timeout=900)
            cls.deployment.sentry.wait()
        except amulet.helpers.TimeoutError:
            amulet.raise_status(
                amulet.SKIP, msg="Environment wasn't stood up in time")
        except:
            raise

        cls.nagios = cls.deployment.sentry['nagios/0']
        cls.haproxy = cls.deployment.sentry['haproxy/0']
        cls.rsyslogfwd = cls.deployment.sentry['rsyslog-forwarder/0']
        cls.nagios.run(
            'sudo mkdir -p /tmp/amulet-test/test-dir;'
            'sudo chmod go-rx /tmp/amulet-test;'
            'echo contents > /tmp/amulet-test/test-file;'
        )
        cls.rsyslogfwd.run(
            'echo more-contents > /tmp/amulet-sub-test;'
        )

    def test_add_unit(self):
        self.deployment.add_unit('haproxy')
        haproxy = self.deployment.sentry['haproxy/1']
        self.assertEqual('1', haproxy.info['unit'])
        self.assertEqual('haproxy/1', haproxy.info['unit_name'])

    def test_info(self):
        self.assertTrue('public-address' in self.nagios.info)
        self.assertEqual('nagios', self.nagios.info['service'])
        self.assertEqual('0', self.nagios.info['unit'])
        self.assertEqual('nagios/0', self.nagios.info['unit_name'])

    def test_file_stat(self):
        path = '/tmp/amulet-test/test-file'
        stat = self.nagios.file_stat(path)
        self.assertTrue(stat.pop('mtime'))
        self.assertEqual(
            stat, {
                'size': 9,
                'uid': 0,
                'gid': 0,
                'mode': '0100644',
            },
        )
        stat = self.nagios.file_stat('metadata.yaml')
        self.assertTrue(stat.pop('mtime'))

    def test_file_contents(self):
        path = '/tmp/amulet-test/test-file'
        self.assertEqual(
            self.nagios.file_contents(path),
            'contents\n',
        )
        self.assertIn('nagios', self.nagios.file_contents('metadata.yaml'))

    def test_subordinate_file_contents(self):
        path = '/tmp/amulet-sub-test'
        self.assertEqual(
            self.rsyslogfwd.file_contents(path),
            'more-contents\n',
        )
        self.assertIn('rsyslog', self.rsyslogfwd.file_contents('metadata.yaml'))

    def test_directory_stat(self):
        path = '/tmp/amulet-test'
        stat = self.nagios.directory_stat(path)
        self.assertTrue(stat.pop('mtime'))

        """
        The block size is dependent on the file system used.
        btrfs defaults to 16k, ext2/3/4 defaults to 4k, etc.
        In this case, trust the stat size returned from the unit.
        """
        self.assertEqual(
            stat, {
                'size': stat['size'],
                'uid': 0,
                'gid': 0,
                'mode': '040700',
            },
        )
        stat = self.nagios.directory_stat('hooks')
        self.assertTrue(stat.pop('mtime'))

    def test_directory_listing(self):
        path = '/tmp/amulet-test'
        self.assertEqual(
            self.nagios.directory_listing(path), {
                'files': ['test-file'],
                'directories': ['test-dir'],
            },
        )
        self.assertIn('install', self.nagios.directory_listing('hooks')['files'])

    def test_relation(self):
        nagios_info = self.nagios.relation(
            'website', 'haproxy:reverseproxy')
        for key in ['hostname', 'port', 'private-address']:
            self.assertTrue(key in nagios_info)

        haproxy_info = self.haproxy.relation(
            'reverseproxy', 'nagios:website')
        self.assertEqual(list(haproxy_info.keys()), ['private-address'])

    def test_run(self):
        self.assertEqual(
            self.nagios.run('echo hello'),
            ('hello', 0),
        )


if __name__ == '__main__':
    unittest.main()
