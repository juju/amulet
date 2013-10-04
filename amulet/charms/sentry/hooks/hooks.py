#!/usr/bin/python

import os
import sys
import json
import glob
import subprocess


relation_dir = '/opt/relations'
unit_number = os.environ['JUJU_REMOTE_UNIT'].split('/')[1]
data_dir = os.path.join(relation_dir, os.environ['JUJU_RELATION'], unit_number)
endpoint, relation = os.environ['JUJU_RELATION'].split('-', 1)

if not os.path.exists(data_dir):
    os.makedirs(data_dir)

with open(os.path.join(data_dir, 'id'), 'w') as f:
    f.write(os.environ['JUJU_RELATION_ID'])

with open(os.path.join(data_dir, 'data'), 'w') as f:
    try:
        data = subprocess.check_output(['relation-get', '--format=json'])
    except:
        pass
    else:
        f.write(data)

if endpoint == "requires":
    otherend = "provides"
else:
    otherend = "requires"

other_data_dir = os.path.join(relation_dir, "%s-%s" % (otherend, relation))
subprocess.call(['juju-log', 'Running: %s %s' % (os.environ['JUJU_RELATION'],
                                                 otherend)])

if not os.path.exists(other_data_dir):
    sys.exit(0)

for unit_data_dir in glob.glob(os.path.join(other_data_dir, '*')):
    unit = os.path.basename(unit_data_dir)
    with open(os.path.join(unit_data_dir, 'id')) as f:
        relation_id = f.read().strip()

    with open(os.path.join(unit_data_dir, 'data')) as f:
        relation_data = json.loads(f.read().strip())

    subprocess.call(['juju-log', json.dumps(relation_data)])
    relation_cmd_line = ['relation-set']
    for key, val in relation_data.items():
        if val is None:
            relation_cmd_line.append('{}='.format(key))
        else:
            relation_cmd_line.append('{}={}'.format(key, val))

    subprocess.call(['juju-log', ' '.join(relation_cmd_line)])
    subprocess.check_call(relation_cmd_line)

    # Send our data to other units
    if data:
        rel_cmd = ['relation-set', '-r', relation_id]
        for key, val in json.loads(data).items():
            if val is None:
                rel_cmd.append('{}='.format(key))
            else:
                rel_cmd.append('{}={}'.format(key, val))

            subprocess.call(['juju-log', ' '.join(rel_cmd)])
            subprocess.check_call(rel_cmd)

