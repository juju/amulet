import unittest


class TestGitCham(unittest.TestCase):

    def makeone(self, fork="http://github.com/juju-solutions/kraken.git",
                name="gitty"):
        from amulet.charm import GitCharm
        return GitCharm(fork, name)
