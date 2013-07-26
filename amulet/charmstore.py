
import os
import json
import urllib3

class CharmStore(object):
    def __init__(self, host='manage.jujucharms.com', secure=True, version=2):
        self.endpoint = '%s://%s/api/%s/' % ('https' if secure else 'http', host,
                        version)
        self.version = version
        self.http = urllib3.PoolManager()

    def search(self, **kwargs):
        allowed_keys = ['name', 'text', 'autocomplete', 'categories', 'owner',
                        'provides', 'requires', 'series', 'summary', 'type',
                        'limit']

        q = ''
        for key, value in kwargs.items():
            if key in allowed_keys:
                q = '%s%s=%s' % ('&' if q else '', key, value)

        try:
            results = self.query('%s?%s' % ('charms', q))
        except Exception:
            raise

        return results['result']

    def charm(self, name, series='precise', owner=None, version=None):
        if version:
            q = '%s/%s/%s-version' % (owner if owner else '', series, name,
                                      version)
        else:
            r = self.search(name=name, series=series)
            if len(r) > 0:
                q = r[0]['charm']['id']
            else:
                return False

        try:
            results = self.query(q)
        except Exception:
            raise

    def query(self, url):
        api_url = '%s%s' % (self.endpoint, url)
        r = self.http.request('GET', api_url)

        if r.data and (r.status >= 200 or r.status < 400):
            return json.loads(r.data.decode('UTF-8'))
        else:
            raise Exception('No data returned')
