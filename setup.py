from distutils.core import setup

setup(name='amulet',
      version='1.1.1',
      description='Tools to help with writing Juju Charm Functional tests',
      install_requires=['requests', 'argparse', 'pycrypto', 'paramiko', 'bzr',
                        'urllib', 'urllib3', 'yaml'],
      package_data={'amulet': ['charms/sentry/hooks/*',
                               'charms/sentry/src/*.*',
                               'charms/sentry/src/*/*']},
      author='Marco Ceppi',
      author_email='marco@ceppi.net',
      url="https://launchpad.net/amulet",
      packages=['amulet'],
      scripts=['bin/amulet'],
      )
