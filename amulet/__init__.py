
from . import waiter

from .deployer import Deployment
from .charmstore import CharmStore
from .helpers import TimeoutError, timeout, default_environment


def wait(*args, **kwargs):
    """Wait until all criteria is met for a given juju environment

    When run without parameters the following defaults are used:
      - juju_env = os.environ['JUJU_ENV']
      - timeout = 300 (5m)
      - Wait will pause execution and wait for ALL units to move to a non-error
      state.

    You can specify which service or units you want to wait for by passing them
    as arguments:

      amulet.wait('service_a', 'service_a/1')

    """
    import os

    if not 'juju_env' in kwargs:
        if 'JUJU_ENV' in os.environ:
            kwargs['juju_env'] = os.environ['JUJU_ENV']
        else:
            kwargs['juju_env'] = default_environment(os.environ['JUJU_HOME'])

    if not 'timeout' in kwargs:
        kwargs['timeout'] = 300

    ready = False
    try:
        with timeout(kwargs['timeout']):
            while not ready:
                try:
                    status = waiter.state(*args, juju_env=kwargs['juju_env'])
                except TimeoutError:
                    raise
                except Exception as e:
                    continue

                for service in status:
                    for unit in status[service]:
                        if status[service][unit] in waiter.SUCESS_STATES:
                            ready = True
                        else:
                            ready = False
                            break
                    if not ready:
                        break

    except TimeoutError:
        raise

    return True
