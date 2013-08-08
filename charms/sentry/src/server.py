
import cherrypy
import base64
import hashlib
import json
import os

import api
import json_rpc


class Instance (api.API):
    def __init__(self):
        self._users = json.load(open("users.json"))

    def _check_credentials(self, username, password):
        password = hashlib.sha512(password.encode()).hexdigest()
        return username in self._users and self._users[username] == password

    def _validate(self, auth):
        if auth.startswith("Basic "):
            auth = auth[6:].encode()
            username, password = base64.b64decode(auth).decode().split(":")
            return self._check_credentials(username, password)
        return False

if __name__ == '__main__':
    cwd = os.path.split(os.path.abspath(__file__))[0]
    # you can make this next line into a comment when testing things
    #cherrypy.config.update({'engine.autoreload_on': False})
    cherrypy.quickstart(Instance(), config={'global': {
        'tools.encode.encoding': 'utf8',
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 9001,
        'server.ssl_certificate': '/etc/ssl/certs/ssl-cert-snakeoil.pem',
        'server.ssl_private_key': '/etc/ssl/private/ssl-cert-snakeoil.key',
        'log.access_file': '/var/log/sentry/access.log',
        'log.error_file': '/var/log/sentry/error.log',
        'tools.gzip.on': True,
    }})
