import os

from setuptools import setup

version_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), 'VERSION'))

with open(version_file) as v:
    VERSION = v.read().strip()

install_requires = [
    'requests',
    'libcharmstore',
    'PyYAML',
    'path.py'
]

tests_require = [
    'coverage',
    'nose',
    'pep8',
]


setup(
    name='amulet',
    version=VERSION,
    description='Tools to help with writing Juju Charm Functional tests',
    install_requires=install_requires,
    package_data={'amulet': ['unit-scripts/amulet/*']},
    author='Marco Ceppi',
    author_email='marco@ceppi.net',
    url="https://github.com/juju/amulet",
    packages=['amulet'],
)
