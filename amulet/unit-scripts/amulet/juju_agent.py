#!/usr/bin/env python

import json
import os

PROC_DIR = '/proc'
JUJU_DIR = '/var/lib/juju/agents/'

d = {}
for pid in [p for p in os.listdir(PROC_DIR) if p.isdigit()]:
    try:
        cmd = open(os.path.join(PROC_DIR, pid, 'cmdline')).read()
    except:
        continue
    if JUJU_DIR in cmd:
        d['hook'] = os.path.basename(cmd)
        break

print(json.dumps(d))
