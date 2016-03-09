Installation
------------

Amulet is available as both a package and via pip. For source packages,
see `GitHub`_.

Ubuntu
~~~~~~

Amulet is available in the Juju Stable PPA for Ubuntu

.. code:: bash

    sudo add-apt-repository ppa:juju/stable
    sudo apt-get update
    sudo apt-get install amulet

Mac OSX
~~~~~~~

Amulet is available via Pip:

.. code:: bash

    sudo pip install amulet

Windows
~~~~~~~

Amulet is available via Pip:

.. code:: bash

    pip install amulet

Source
~~~~~~

Amulet is built with Python3, so please make sure it’s installed prior
to following these steps. While you can run Amulet from source, it’s not
recommended as it requires several changes to environment variables in
order for Amulet to operate as it does in the packaged version.

To install Amulet from source, first get the source:

.. code:: bash

    git clone https://github.com/juju/amulet.git

Move in to the ``amulet`` directory and run:

.. code:: bash

    sudo python3 setup.py install

You can also access the Python libraries; however, your ``PYTHONPATH``
will need to be amended in order for it to find the amulet directory.

.. _GitHub: https://github.com/juju/amulet/releases
