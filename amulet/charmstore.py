
import os
import json
import yaml
import urllib3


# Move to charm
def get_relation(charm, relation):
    if os.path.exists(os.path.join(charm, 'metadata.yaml')):
        relations = {}
        with open(os.path.join(charm, 'metadata.yaml')) as m:
            metadata = yaml.safe_load(m.read())
        for key in ['requires', 'provides']:
            if key in metadata:
                relations[key] = metadata[key]
    else:
        cs = CharmStore()

        try:
            c = cs.charm(charm)
            relations = c['charm']['relations']
        except:
            raise

    if not relations:
        raise Exception('No relations for charm')

    for rel_type in relations:
        for rel_name in relations[rel_type]:
            if rel_name == relation:
                return rel_type, relations[rel_type][rel_name]['interface']

    return (None, None)


class CharmStore(object):
    def __init__(self, host='manage.jujucharms.com', secure=True, version=2):
        self.endpoint = '%s://%s/api/%s/' % ('https' if secure else 'http',
                        host, version)
        self.version = version
        self.http = urllib3.PoolManager()
        self.cache = {}

    def search(self, **kwargs):
        allowed_keys = ['name', 'text', 'autocomplete', 'categories', 'owner',
                        'provides', 'requires', 'series', 'summary', 'type',
                        'limit']

        q = ''
        for key, value in kwargs.items():
            if key in allowed_keys:
                q = '%s%s%s=%s' % (q, '&' if q else '', key, value)

        try:
            results = self.query('%s?%s' % ('charms', q))
        except Exception:
            raise

        return results['result']

    def charm(self, name, series='precise', owner=None, version=None,
              use_cache=True):
        if name in self.cache and not version and use_cache:
            return self.cache[name]

        if version:
            q = 'charm/%s/%s/%s-%s' % (owner if owner else '', series, name,
                                       version)
            try:
                results = self.query(q)
            except Exception:
                raise

            # Don't cache version lookups
            return results
        else:
            r = self.search(name=name, series=series)
            if len(r) > 0:
                results = r[0]
            else:
                return False

        self.cache[name] = results
        return results

    def query(self, url):
        api_url = '%s%s' % (self.endpoint, url)
        r = self.http.request('GET', api_url)

        if r.data and (r.status >= 200 or r.status < 400):
            return json.loads(r.data.decode())
        else:
            raise Exception('No data returned')


class Charm(object):
    def __init__(self, metadata):
        pass

    def get_relation(self, relation):
        pass
