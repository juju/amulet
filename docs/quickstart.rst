Getting Started
===============

Get familiar with Amulet quickly by following this short series of
increasingly feature-rich examples.

Remember that Amulet tests are executable files stored in the
`/tests` directory of the charm or bundle they are testing.


Deploying a Service
-------------------

The "Hello, world" of Amulet:

.. code:: python

    #!/usr/bin/env python

    import amulet

    # Create a new deployment. Use trusty series charms by default.
    d = amulet.Deployment(series="trusty")

    # Add a mysql service to the deployment.
    d.add('mysql')

    # Set the mysql service to be exposed (accessible to the outside world).
    d.expose('mysql')

    try:
        # Execute the deployment with a timeout of 600 seconds.
        d.setup(timeout=600)

        # After services are deployed, related, and configured, allow up to
        # 600 seconds for hooks to finish running. This call will block until
        # all hooks complete (the deployment is "settled") or the timeout is
        # hit.
        d.sentry.wait(timeout=300)
    except amulet.TimeoutError:
        # If we end up here, our setup() or wait() call timed out.
        raise

    # Deployment completed within the timeout, now we can test it!


This is a valid (albeit marginally useful) Amulet test. It doesn't test much,
but it does test that the mysql service deploys successfully (without any hook
failures) within the timeout.


Relating and Configuring Services
---------------------------------

In the previous example we simply dumped all of our Amulet code into the
module scope of our test file. For the remaining examples we'll adopt a better
style, one that will be familiar to those who have used Python's ``unittest``
module.

In this example we deploy two services, relate them, and change some configuration
on one of the services.

.. code:: python

    import unittest
    import amulet


    class TestDeployment(unittest.TestCase):

        @classmethod
        def setUpClass(cls):
            cls.d = amulet.Deployment(series='trusty')

            cls.d.add('mysql')
            cls.d.add('mediawiki')
            cls.d.add('haproxy')

            # set up service relations
            cls.d.relate('mysql:db', 'mediawiki:db')
            cls.d.relate('mediawiki:website', 'haproxy:reverseproxy')

            # change some configuration on mediawiki
            cls.d.configure('mediawiki', {
                'title': 'My Wiki',
                'skin': 'Nostolgia',
            })

            cls.d.expose('haproxy')

            cls.d.setup()
            cls.d.sentry.wait()


    if __name__ == '__main__':
        unittest.main()


Testing the Deployment
----------------------

Now that we know how to set up, configure, and deploy our workload, let's see
how to run tests against it.

The :class:`Deployment.sentry <amulet.sentry.Talisman>` object supplies us with a
:class:`~amulet.sentry.UnitSentry` for each unit in our deployment, which we
can use to interact with the unit in ways that are useful for testing.

This example will deploy the same workload as the previous example, but now
we'll add some test methods to exercise and inspect the deployment.

.. code:: python

    import unittest

    import requests
    import amulet


    class TestDeployment(unittest.TestCase):

        @classmethod
        def setUpClass(cls):
            """Set up our deployment.

            This happens once, after which all 'test_' methods are run.

            """
            cls.d = amulet.Deployment(series='trusty')

            cls.d.add('mysql')
            cls.d.add('mediawiki')
            cls.d.add('haproxy')

            cls.d.relate('mysql:db', 'mediawiki:db')
            cls.d.relate('mediawiki:website', 'haproxy:reverseproxy')
            cls.d.expose('haproxy')

            cls.d.setup()
            cls.d.sentry.wait()

        def test_scale_up(self):
            """Test that haproxy config is updated when a new web unit is added.

            """
            # add another mediawiki unit and wait for hooks to complete
            self.d.add_unit('mediawiki')
            self.d.sentry.wait()

            # get the UnitSentry for the last mediawiki unit (the one we just
            # added)
            mediawiki = self.d.sentry['mediawiki'][-1]

            # get UnitSentry for the haproxy unit
            haproxy = self.d.sentry['haproky'][0]

            # get contents of the haproxy config on the runnning unit
            haproxy_config = haproxy.file_contents('/etc/haproxy/haproxy.cfg')

            # get the mediawiki private address from it's relation with haproxy
            mediawiki_address = mediawiki.relation(
                'website', 'haproxy:reverseproxy')['private-address']

            # test that the haproxy config contains the address of the
            # new mediawiki unit that we added
            self.assertTrue(mediawiki_address in haproxy_config)

            # here's an alternate way to do the same thing
            output, exit_code = haproxy.run(
                'grep %s /etc/haproxy/haproxy.cfg' % mediawiki_address)
            self.assertTrue(exit_code == 0)

        def test_reconfigure(self):
            """Test that website is updated when mediawiki config is changed.

            """
            # change mediawiki config, setting a new title, and wait for hooks
            # to complete
            new_title = 'My New Title'
            cls.d.configure('mediawiki', {
                'title': new_title,
            })
            self.d.sentry.wait()

            # get url to the mediawiki website (fronted by haproxy)
            haproxy = self.d.sentry['haproxy'][0]
            haproxy_url = 'http://{public-address}'.format(**haproxy.info)

            # fetch website homepage
            homepage = requests.get(haproxy_url)

            # test that homepage contains our new title
            self.assertTrue(new_title in homepage)


    if __name__ == '__main__':
        unittest.main()


Next Steps
----------

These examples have shown a few basic ways to manipulate your deployment and
interact with deployed units using Amulet. For more details on the full Amulet
API, please consult the documentation for
:class:`~amulet.deployer.Deployment` and :class:`~amulet.sentry.UnitSentry`.
