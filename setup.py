from setuptools import setup

install_requires = [
    'requests',
    'urllib3',
    'charmworldlib',
    'PyYAML'
]

tests_require = [
    'coverage',
    'nose',
    'pep8',
]


setup(
    name='amulet',
    version='1.2.0',
    description='Tools to help with writing Juju Charm Functional tests',
    install_requires=install_requires,
    package_data={'amulet': ['charms/sentry/hooks/*',
                             'charms/sentry/src/*.*',
                             'charms/sentry/src/*/*']},
    author='Marco Ceppi',
    author_email='marco@ceppi.net',
    url="https://launchpad.net/amulet",
    packages=['amulet'],
    entry_points={
        'console_scripts': [
            'amulet=amulet.cli:main'
        ]
    }
)
