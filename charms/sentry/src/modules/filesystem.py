
import os
import json
import cherrypy
import json_rpc
import subprocess

class Module (object):

    @json_rpc.expose_anonymous_dont_jsonify
    def file(self, action=None, name=None):
        if not cherrypy.request.method in ['GET']:
            raise cherrypy.HTTPError(405)

        if not name:
            raise cherrypy.HTTPError(400)

        if action and action != 'contents':
            raise cherrypy.HTTPError(400)

        if not os.path.isfile(name):
            raise cherrypy.HTTPError(404)

        if not action:
            return json.dumps(self.fs_data(name), indent=4)

        with open(name, 'r') as f:
            contents = f.read()

        return contents

    @json_rpc.expose_anonymous
    def directory(self, action=None, name=None):
        if not cherrypy.request.method in ['GET']:
            raise cherrypy.HTTPError(405)

        if not name:
            raise cherrypy.HTTPError(400)

        if action and action != 'contents':
            raise cherrypy.HTTPError(400)

        if not os.path.isdir(name):
            raise cherrypy.HTTPError(404)

        if not action:
            return self.fs_data(name)

        contents = {'files': [], 'directories': []}
        for fd in os.listdir(name):
            if os.path.isfile('%s/%s' % (name, fd)):
                contents['files'].append(fd)
            else:
                contents['directories'].append(fd)

        return contents

    def fs_data(self, path):
        fs_stat = os.stat(path)

        return {'mtime': fs_stat.st_mtime,
                'size': fs_stat.st_size,
                'uid': fs_stat.st_uid,
                'gid': fs_stat.st_gid,
                'mode': oct(fs_stat.st_mode)}
