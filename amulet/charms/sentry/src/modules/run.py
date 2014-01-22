
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
            code = 0
            results = subprocess.check_output(command, shell=True)
        except subprocess.CalledProcessError as e:
            cherrypy.response.status = 500
            code = e.returncode
            results = e.output

        return {'code': code, 'output': results.decode().strip()}
