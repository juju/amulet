# Amulet, a testing harness

[![Build Status](https://travis-ci.org/juju/amulet.png?branch=master)](https://travis-ci.org/juju/amulet) [![Coverage Status](https://coveralls.io/repos/marcoceppi/amulet/badge.png)](https://coveralls.io/r/marcoceppi/amulet)

Amulet is a set of tools designed to simplify the testing process for charm authors. Amulet aims to be a

- testing harness to ease the use of writing and running tests.
- validation of charm relation data, not just what a charm expects/receives.
- method to exercise and test charm relations outside of a deployment.

Ultimately, Amulet is to testing as Charm Helpers are to charm hooks. While these tools are designed to help make test writing easier, much like charm helpers are designed to make hook writing easier, they are not required to write tests for charms. This library is offered as a completely optional set of tools for you to use.

## What's in a name?

By definition, An amulet can be any object but its most important characteristic is its alleged power to protect its owner from danger or harm.

By this definition, Amulet is designed to be a library which protects charm authors from having broken charms by making test writing easier.

## Install
Amulet is available as both a package and via pip. For source packages, see [Github](https://github.com/juju/amulet/releases).
### Ubuntu
Amulet is available in the Juju Stable PPA for Ubuntu

    sudo add-apt-repository ppa:juju/stable
    sudo apt-get update
    sudo apt-get install amulet

### Mac OSX
Amulet is available via Pip

    sudo pip install amulet

### Windows
Amulet is available via Pip

    pip install amulet

### Source

Amulet is built with Python3, make sure it's installed prior to following these steps. While you can run Amulet from source, it's not recommended as it requires several changes to environment variables in order for Amulet to operate as it does in the packaged version.

To install Amulet from source, first get the source:

    git clone https://github.com/juju/amulet.git
    cd amulet
    make sysdeps

Move in to the `amulet` directory and run `sudo python3 setup.py install`. You can also access the Python libraries; however, your `PYTHONPATH` will need to be amended in order for it to find the amulet directory.

### Hacking

Get the source and build your developmenmt environment with:

    git clone https://github.com/juju/amulet.git
    cd amulet
    make sysdeps
    make install
    juju bootstrap -e ec2
    make test

# Usage

Amulet comes packaged with several tools. In order to provide the most flexibility, Amulet offers both direct Python library access and generic access via a programmable API for other languages (for example, bash). Below are two examples of how each is implemented. Please refer to the developer documentation for precise examples of how each function is implemented.

## Python

Amulet is made available to Python via the Amulet module which you can import.

    import amulet

The `amulet` module seeds each module/command directly, so `Deployment` is made available in `amulet/deployer.py` is accessible directly from `amulet` using

    from amulet import Deployment

Though `deployer` is also available in the event you wish to execute any of the helper functions

    from amulet import deployer
    d = deployer.Deployment()

## Programmable API

A limited number of functions are made available through a generic forking API. The following examples assume you're using a BOURNE Shell, though this syntax could be used from within other languages with the same expected results.

Unlike the Python modules, only some of the functions of Amulet are available through this API, though efforts are being made to make the majority of the core functionality available.

This API follows the subcommand workflow, much like Git or Bazaar. Amulet makes an `amulet` command available and each function is tied to a sub-command. To mimic the Python example you can create a a new Deployment by issuing the following command:

    amulet deployment

Depending on the syntax and workflow for each function you can expect to provide either additional sub-commands, command-line flags, or a combination of the two.

Please refer to the Developer Documentation for a list of supported subcommands and the syntax to use each.

# Core functionality

This section is designed to outline the core functions of Amulet. Again, please refer to the developer documentation for an exhaustive list of functions and methods.

## amulet.deployer

The Deployer module houses several classes for interacting and setting up an environment. These classes and methods are outlined below

### amulet.deployer.Deployment()

Deployment (`amulet deployment`, `from amulet import Deployment`) is an abstraction layer to the [juju-deployer](http://launchpad.net/juju-deployer) Juju plugin and a service lifecycle management tool. It's designed to allow an author to describe their deployment in simple terms:

```python
import amulet

d = amulet.Deployment()
d.add('mysql')
d.add('mediawiki')
d.relate('mysql:db', 'mediawiki:db')
d.expose('mediawiki')
d.configure('mediawiki', {
  title: "My Wiki",
  skin: "Nostolgia"
})
d.setup()
```

That information is then translated to a Juju Deployer deployment file then, finally, `juju-deployer` executes the described setup. Amulet strives to ensure it implements the correct version and syntax of Juju Deployer to avoid charm authors having to potentially intervene each time an update to juju-deployer is made.

~~Once an environment has been setup, `deployer` can still drive the environment outside of of juju-deployer. So the same commands (`add`, `relate`, `configure`,
`expose`) will instead interact directly with the environment by using either the Juju API or the juju commands directly.~

#### Deployment(juju_env=None, series='precise', sentries=True, juju_deployer='juju-deployer', sentry_template=None)

#### Deployment.add(service, charm=None, units=1, constraints=None)

Add a new service to the deployment schema.

- `service` Name of the service to deploy
- `charm` If provided, will be the charm used. Otherwise `service` is used as the charm
- `units` Number of units to deploy
- `constraints` A dictionary that specifies the machine constraints.

##### Example deployment

```python
import amulet

d = amulet.Deployment()
d.add('wordpress')
d.add('second-wp', charm='wordpress')
d.add('personal-wp', charm='~marcoceppi/wordpress', units=2)
```
##### Example deployment using constraints

```python
import amulet
from collections import OrderedDict

d = amulet.Deployment()
d.add('charm', units=2, constraints=OrderedDict([
    ("cpu-power", 0),
    ("cpu-cores", 4),
    ("mem", "512M")
]))
```


#### Deployment.build_relations()

Private method invoked during `deployer_map`. Creates relation mapping.

#### Deployment.build_sentries()

Private method invoked during `deployer_map`. Creates sentries for services.

#### Deployment.configure(service, options)

Change configuration options for a service

- `service` The service to configure
- `options` Dict of options

```python
import amulet

d = amulet.Deployment()
d.add('postgresql')
d.configure('postgresql', {'autovacuum': True, 'cluster_name': 'cname'})
```

#### Deployment.deployer_map(services, relations)

Create deployer file from provided services and relations

- `services` Object of service and service data
- `relations` List of relations to map

#### Deployment.expose(service)

Indicate if a service should be exposed after deployment

- `service` Name of service to expose

```python
import amulet

d = amulet.Deployment()
d.add('varnish')
d.expose('varnish')
```

#### Deployment.load(deploy_cfg)

Import an existing deployer object

- `deploy_cfg` Already parsed deployer yaml/json file

#### Deployment.relate(*args)

Relate two services together

- `args` `service:relation` to be related

If more than two arguments are given, it's assumed they're to be added to the first argument as a relation.

```python
import amulet

d = amulet.Deployment()
d.add('postgresql')
d.add('mysql')
d.add('wordpress')
d.add('mediawiki')
d.add('discourse')

d.relate('postgresql:db-admin', 'discourse:db')
d.relate('mysql:db', 'wordpress:db', 'mediawiki:database')
```

#### Deployment.setup(timeout=600)

This will create the deployer mapping, create any sentries that are required, and execute juju-deployer with the generated mapping.

- `timeout` in seconds, how long to wait for setup

```python
import amulet

d = amulet.Deployment()
d.add('wordpress')
d.add('mysql')
d.configure('wordpress', {
  debug: True
})
d.relate('wordpress:db', 'mysql:db')
try:
    d.setup(timeout=900)
except amulet.helpers.TimeoutError:
    # Setup didn't complete before timeout
    pass
```

## amulet.sentry

Sentries are an additional service built in to the Deployment tool which allow an author the ability to dig deeper in to a deployment environment. This is done by adding a set of tools to each service/unit deployed via a subordinate charm and a final "relation sentry" charm is deployed which all relations are proxied through. In doing so you can inspect on each service/unit deployed as well as receive detailed information about what data is being sent by which units/service during a relation.

Sentries can be accessed from within your deployment using the sentry object. Using the above example from ## Deployer, each service and unit can be accessed using the following:

```python
import amulet

d = amulet.Deployment()
d.add('mediawiki')
d.add('mysql')
d.setup()

d.sentry.unit['mysql/0']
d.sentry.unit['mediawiki/0']
```

Sentries provide several methods for which you can use to gather information about an environment. Again, please refer to the Developer Documentation for a complete list of endpoints available. The following are a few examples.

# Examples

Here are a few examples of Amulet tests

## WordPress

### tests/00-setup

```bash
#!/bin/bash

sudo apt-get install amulet python-requests
```

### tests/01-simple

```python

import os
import amulet
import requests

from .lib import helper

d = amulet.Deployment()
d.add('mysql')
d.add('wordpress')
d.relate('mysql:db', 'wordpress:db')
d.expose('wordpress')

try:
    # Create the deployment described above, give us 900 seconds to do it
    d.setup(timeout=900)
    # Setup will only make sure the services are deployed, related, and in a
    # "started" state. We can employ the sentries to actually make sure there
    # are no more hooks being executed on any of the nodes.
    d.sentry.wait()
except amulet.helpers.TimeoutError:
    amulet.raise_status(amulet.SKIP, msg="Environment wasn't stood up in time")
except:
    # Something else has gone wrong, raise the error so we can see it and this
    # will automatically "FAIL" the test.
    raise

# Shorten the names a little to make working with unit data easier
wp_unit = d.sentry.unit['wordpress/0']
mysql_unit = d.sentry.unit['mysql/0']

# WordPress requires user input to "finish" a setup. This code is contained in
# the helper.py file found in the lib directory. If it's not able to complete
# the WordPress setup we need to quit the test, not as failed per se, but as a
# SKIPed test since we can't accurately setup the environment
try:
    helper.finish_setup(wp_unit.info['public-address'], password='amulet-test')
except:
    amulet.raise_status(amulet.SKIP, msg="Unable to finish WordPress setup")

home_page = requests.get('http://%s/' % wp_unit.info['public-address'])
home_page.raise_for_status() # Make sure it's not 5XX error
```

### tests/lib/helper.py

```python

import requests


def finish_setup(unit, user='admin', password=None):
    h = {'User-Agent': 'Mozilla/5.0 Gecko/20100101 Firefox/12.0',
         'Content-Type': 'application/x-www-form-urlencoded',
         'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*',
         'Accept-Encoding': 'gzip, deflate'}

    r = requests.post('http://%s/wp-admin/install.php?step=2' % unit,
                      headers=h, data={'weblog_title': 'Amulet Test %s' % unit,
                      'user_name': user, 'admin_password': password,
                      'admin_email': 'test@example.tld',
                      'admin_password2': password,
                      'Submit': 'Install WordPress'})

    r.raise_for_status()
```
