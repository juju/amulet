#!/bin/bash

set -e

if [[ $JUJU_VERSION == 2 ]]; then
    # the "sudo sudo bash" is to ensure that the lxd group is active
    sudo -E sudo -u $USER -E bash -c "juju bootstrap localhost test"
else
    juju generate-config
    juju switch local
    juju bootstrap
fi
