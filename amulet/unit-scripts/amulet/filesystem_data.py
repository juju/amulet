#!/usr/bin/env python

import json
import os
import sys

s = os.stat(sys.argv[1])
d = {
    'mtime': s.st_mtime,
    'size': s.st_size,
    'uid': s.st_uid,
    'gid': s.st_gid,
    'mode': oct(s.st_mode)
}
print(json.dumps(d))
