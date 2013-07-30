
import cherrypy
import json_rpc
import subprocess

class Module (object):

    # Expose secure when we get admin-secret working
    @json_rpc.expose_anonymous
    def run(self):
        if not cherrypy.request.method in ['POST', 'PUT']:
            raise cherrypy.HTTPError(405)

        command = cherrypy.request.body.read().decode()
        try:
            results = subprocess.check_output(command)
        except:
            raise cherrypy.HTTPError(500)

        return {'result': results}
