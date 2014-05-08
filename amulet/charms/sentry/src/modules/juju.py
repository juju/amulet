
import os
import json_rpc

PROC_DIR = '/proc'


class Module (object):
    @json_rpc.expose_anonymous
    def juju(self):
        pids = [pid for pid in os.listdir(PROC_DIR) if pid.isdigit()]

        hook = None
        for pid in pids:
            with open(os.path.join(PROC_DIR, pid, 'cmdline'), 'r') as p:
                cmd = p.read()
                if '/var/lib/juju/agents/' in cmd:
                    hook = os.path.basename(cmd)

        if hook:
            return {'hook': hook}
        else:
            return {}
