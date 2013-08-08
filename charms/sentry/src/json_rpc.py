
import cherrypy
import functools
import json


def secure(function):
    @functools.wraps(function)
    def wrapped(self, *args, **kwargs):
        auth = cherrypy.request.headers.get("Authorization")
        if auth is None or not self._validate(auth):
            cherrypy.response.headers["WWW-Authenticate"] = (
                "Basic realm=\"Secure Area\"")
            raise cherrypy.HTTPError(401, "Authorization Required")
        else:
            return function(self, *args, **kwargs)
    return wrapped


def jsonify(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return json.dumps(function(*args, **kwargs), indent=4).encode()
    return wrapped


def dont_jsonify(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return function(*args, **kwargs).encode()
    return wrapped


def expose_secure(function):
    return secure(cherrypy.expose(jsonify(function)))


def expose_secure_dont_jsonify(function):
    return secure(cherrypy.expose(dont_jsonify(function)))


def expose_anonymous(function):
    return cherrypy.expose(jsonify(function))


def expose_anonymous_dont_jsonify(function):
    return cherrypy.expose(dont_jsonify(function))
