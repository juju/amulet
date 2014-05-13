import unittest
import yaml

from amulet.sentry import Talisman
from mock import patch


mock_status = yaml.load("""\
services:
  meteor:
    units:
      meteor/0:
        public-address: 10.0.3.152
      meteor/1:
        public-address: 10.0.3.177
  relation-sentry:
    units:
      relation-sentry/0:
        public-address: 10.0.3.92
""")


class TalismanTest(unittest.TestCase):

    @patch.object(Talisman, 'wait_for_status')
    @patch('amulet.sentry.helpers.default_environment')
    def test_init(self, default_env, wait_for_status):
        default_env.return_value = 'local'
        wait_for_status.return_value = mock_status

        sentry = Talisman(['meteor'])

        self.assertTrue('meteor/0' in sentry.unit)
        self.assertTrue('meteor/1' in sentry.unit)

    @patch.object(Talisman, 'wait_for_status')
    @patch('amulet.sentry.helpers.default_environment')
    def test_getitem(self, default_env, wait_for_status):
        default_env.return_value = 'local'
        wait_for_status.return_value = mock_status

        sentry = Talisman(['meteor'])

        self.assertEqual(sentry['meteor/0'], sentry.unit['meteor/0'])
        self.assertEqual(sentry['meteor'], list(sentry.unit.values()))
