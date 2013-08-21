# Introduction

Amulet is a set of tools designed to simplify the testing process for charm
authors. Ultimately, Amulet is to testing as Charm Helpers are to charm hooks.
While these tools are designed to help make test writing easier, much like
charm helpers are designed to make hook writing easier, they are not required
to write tests for charms. This library is offered as a completely optional
set of tools for you to use.

## What's in a name?

By definition, An amulet can be any object but its most important
characteristic is its alleged power to protect its owner from danger or harm.

By this definition, Amulet is designed to be a library which protects charm
authors from having broken charms by making test writing easier.

# Installation

## Packaged

Amulet is regularly packaged in a PPA with the aim of eventual inclusion in
distro. Currently that PPA is ppa:juju/pkgs though that may change in the
future. Once you've added the appropriate source for Amulet, install it using
apt-get:

    sudo apt-get update
    sudo apt-get install amulet

## Source

While ou can run Amulet from source, it's not recommended as it requires
several changes to environment variables in order for Amulet to operate as it
does in the packaged version.

To install Amulet from source, first branch the source:

    bzr branch lp:amulet

Move in to the `amulet` directory and execute `bin/amulet`. You can also access
the Python libraries; however, your `PYTHONPATH` will need to be ammended in
order for it to find the amulet directory.

# Usage

Amulet comes packaged with several tools. In order to provide the most
flexibility, Amulet offers both direct Python library access and generic access
via a programmable API for other languages (for example, bash). Below are two
examples of how each is implemented. Please refer to the developer
documentation for precise examples of how each function is implemented.

## Python

Amulet is made available to Python via the Amulet module which you can import.

    import amulet

The `amulet` module seeds each module/command directly, so `Deployment` made
available in `amulet/deployer.py` is accessible directly from `amulet` using

    from amulet import Deployment

Though `deployer` is also available in the event you wish to execute any of the
helper functions

    from amulet import deployer
    d = deployer.Deployment()

## Programmable API

A limited number of functions are made available through a generic forking API.
The following examples assume you're using a BOURNE Shell, though this syntax
could be used from within other languauges with the same expected results.

Unlike the Python modules, only some of the functions of Amulet are available
through this API, though we've made the majority of the core functionality
available.

This API follows the subcommand workflow, much like Git or Bazaar. Amulet makes
an `amulet` command available and each function is tied to a sub-command. To
mimic the Python example you can createa a new Deployment by issuing the
following command:

    amulet deployment

Depending on the syntax and worflow for each function you can expect to provide
either additional sub-commands, command-line flags, or a combination of the
two.

Please refer to the Developer Documentation for a list of supported subcommands
and the syntax to use each.

# Core functionality

This section is deigned to outline the core functions of Amulet. Again, please
refer to the developer documentation for an exhaustive list of functions and
methods.

## Deployment

Deployment (`amulet deployment`, `from amulet import Deployment`) is an
abstraction layer to the [juju-deployer](http://launchpad.net/juju-deployer)
Juju plugin and a service lifecycle management tool. It's designed to allow an
author to describe their deployment in simple terms:

    import amulet

    d = amulet.Deployment()
    d.add('mysql')
    d.add('mediawiki')
    d.relate('mysql:db', 'mediawiki:db')
    d.expose('mediawiki')
    d.configure('mediawiki', title="My Wiki", skin="Nostolgia")
    d.setup()

and have that information translated to a Juju Deployer deployment file then
finally have `juju-deployer` execute the described setup. Amulet strives to
insure it implements the correct version and syntax of Juju Deployer to avoid
charm authors having to intervine each time an update to juju-deployer is made.

Once an environment has been setup, deployer can still drive the environment
outside of of juju-deployer. So the same commands (`add`, `relate`, `configure`,
`expose`) will instead interact directly with the environment by using either
the Juju API or the juju commands directly. 

### Sentries

Sentries are an additional service built in to the Deployment tool which allow
an author the ability to dig deeper in to a deployment environment. This is
done by adding a set of tools to each service/unit deployed via a subordinate
charm and a final "relation sentry" charm is deployed which all relations are
proxied through. In doing so you can introsepct on each service/unit deployed
as well as recieve detailed information about what data is being sent by which
units/service during a relation.

Sentries can be accessed from within your deployment using the sentry object.
Using the above example from ## Deployment, each service and unit can be
accessed using the following:

    d.sentry.unit['mysql/0']
    d.sentry.unit['mediawiki/0']
    d.sentry.service['mysql']
    d.sentry.service['mediawiki']
    d.sentry.relations

Sentries provide several methods for which you can use to gather information
about an environment. Again, please refer to the Developer Documentation for a
complete list of endpoints available. The following are a few examples.


## Wait
