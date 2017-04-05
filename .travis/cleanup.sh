#!/bin/bash -uex

if [[ $JUJU_VERSION == 2 ]]; then
    # the "sudo sudo bash" is to ensure that the lxd group is active
    sudo -E sudo -u $USER -E bash -c "juju destroy-controller --destroy-all-models -y test"
else
    juju destroy-environment --force
fi
