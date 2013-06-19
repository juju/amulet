from distutils.core import setup

setup(name='amulet',
      version='0.0.1',
      description='Tools to help with writing Juju Charm Functional tests',
      author='Marco Ceppi',
      author_email='marco@ceppi.net',
      url="https://launchpad.net/amulet",
      packages=['amulet'],
      scripts=['bin/amulet'],
      )
