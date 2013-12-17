# Amulet, a testing harness
Amulet is a set of tools designed to simplify the testing process for charm authors. Amulet aims to be a 

- testing harness to ease the use of writing and running tests.
- validation of charm relation data, not just what a charm expects/receives.
- method to exercise and test charm relations outside of a deployment.

Ultimately, Amulet is to testing as Charm Helpers are to charm hooks. While these tools are designed to help make test writing easier, much like charm helpers are designed to make hook writing easier, they are not required to write tests for charms. This library is offered as a completely optional set of tools for you to use.

## What's in a name?

By definition, An amulet can be any object but its most important characteristic is its alleged power to protect its owner from danger or harm.

By this definition, Amulet is designed to be a library which protects charm authors from having broken charms by making test writing easier.

## Install
Amulet is available as both a package and via pip. For source packages, see [Github](https://github.com/marcoceppi/amulet/releases.
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

    git clone https://github.com/marcoceppi/amulet.git

Move in to the `amulet` directory and run `sudo python3 setup.py install`. You can also access the Python libraries; however, your `PYTHONPATH` will need to be amended in order for it to find the amulet directory.

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

A limited number of functions are made available through a generic forking API. The following examples assume you're using a BOURNE Shell, though this syntax could be used from within other languauges with the same expected results.

Unlike the Python modules, only some of the functions of Amulet are available through this API, though efforts are being made to make the majority of the core functionality available.

This API follows the subcommand workflow, much like Git or Bazaar. Amulet makes an `amulet` command available and each function is tied to a sub-command. To mimic the Python example you can create a a new Deployment by issuing the following command:

    amulet deployment

Depending on the syntax and worflow for each function you can expect to provide either additional sub-commands, command-line flags, or a combination of the two.

Please refer to the Developer Documentation for a list of supported subcommands and the syntax to use each.

# Core functionality

This section is deigned to outline the core functions of Amulet. Again, please refer to the developer documentation for an exhaustive list of functions and methods.

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
d.configure('mediawiki', title="My Wiki", skin="Nostolgia")
d.setup()
```

That information is then translated to a Juju Deployer deployment file then, finally, `juju-deployer` executes the described setup. Amulet strives to insure it implements the correct version and syntax of Juju Deployer to avoid charm authors having to potentially intervene each time an update to juju-deployer is made.

~~Once an environment has been setup, `deployer` can still drive the environment outside of of juju-deployer. So the same commands (`add`, `relate`, `configure`,
`expose`) will instead interact directly with the environment by using either the Juju API or the juju commands directly.~

#### Deployment(juju_env=None, series='precise', sentries=True, juju_deployer='juju-deployer', sentry_template=None)

a

#### Deployment.add(service, charm=None, units=1)

Add a new service to the deployment schema.

- `service` Name of the service to deploy
- `charm` If provided, will be the charm used. Otherwise `service` is used as the charm
- `units` Number of units to deploy

```python
import amulet

d = amulet.Deployment()
d.add('wordpress')
d.add('second-wp', charm='wordpress')
d.add('personal-wp', charm='~marcoceppi/wordpress', units=2)
```

#### Deployment.build_relations()

Private method invoked during `deployer_map`. Creates relation mapping.

#### Deployment.build_sentries()

Private method invoked during `deployer_map`. Creates sentries for services.

#### Deployment.configure(service, **options)

Change configuration options for a service

- `service` The service to configure
- `**options` Seed with `key=val`

```python
import amulet

d = amulet.Deployment()
d.add('postgresql')
d.configure('postgresql', autovacuum=True, cluster_name='cname')
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
d.configure('wordpress', debug=True)
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
