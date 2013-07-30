
import cherrypy


class Module (object):

    @cherrypy.expose
    def index(self):
        return open("index.html")
