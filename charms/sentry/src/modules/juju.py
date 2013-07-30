
import os
import json
import cherrypy
import json_rpc
import subprocess

class Module (object):

    @json_rpc.expose_anonymous
    def juju(self):
        pids = [pid for pid in os.listdir('/proc') if pid.isdigit()]

        hook = None
        for pid in pids:
            with open(os.path.join('/proc', pid, 'cmdline'), 'r') as p:
                cmd = p.read()
                if '/var/lib/juju/agents/' in cmd:
                    hook = os.path.basename(cmd)

        if hook:
            return {'hook': hook}
        else:
            return {}
