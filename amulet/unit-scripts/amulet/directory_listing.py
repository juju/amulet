#!/usr/bin/env python

import json
import os
import sys

path = sys.argv[1]

contents = {'files': [], 'directories': []}
for fd in os.listdir(path):
    if os.path.isfile('{}/{}'.format(path, fd)):
        contents['files'].append(fd)
    else:
        contents['directories'].append(fd)
print(json.dumps(contents))
