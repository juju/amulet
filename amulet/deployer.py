
import os
import re
import yaml
import json

import helpers


class Deployer(object):
    def __init__(self, environment=None, series='precise', sentries=True):
        self.services = {}
        self.relations = {}
        self.series = series
        self.sentries = sentries
        self.environment = environment or helpers.default_environment()
        self.interfaces = []

    def load(self, deploy_cfg):
        self.environment = deploy_cfg.keys()[0]
        schema = deploy_cfg[self.environment]
        self.services = schema['services']
        self.series = schema['series']

        for rel in schema['relations']:
            self.relations[rel] = schema['relations'][rel]['consumes']

    def add(self, service, charm=None, units=1):
        # Do charm revision look ups?
        if service in self.services:
            raise ValueError('Service is already set to be deployed')
        if charm and charm.startswith('cs:~'):
            m = re.search('^cs:(~[\w-]+)/([\w-]+)', charm)
            charm = 'lp:%s/charms/%s/%s/trunk' % (m.group(1), self.series,
                                                  m.group(2))

        self.services[service] = {'branch': charm or 'lp:charms/%s' % service,
                                  'units': units}

    def relate(self, from_charm, to_charm):
        if not from_charm in self.relations:
            self.relations[from_charm] = []

        self.relations[from_charm].append(to_charm)

    def schema(self):
        return self.deployer_map(self.services, self.relations)

    def configure(self, service, **options):
        if service not in self.services:
            raise ValueError('Service has not yet been described')
        if not 'options' in self.services[service]:
            self.services[service]['options'] = options
        else:
            self.services[service]['options'].update(options)

    def setup(self, timeout=300):
        pass

    def deployer_map(self, services, relations):
        self.build_sentries(self.relations)
        deployer_map = {
            self.environment: {
                'series': self.series,
                'services': self.services,
                'relations': self.build_relations(self.relations)
            }
        }

        return deployer_map

    def _find_common_interface(self, *args):
        pass

    def build_relations(self, relation_data=None):
        if not relation_data:
            relation_data = self.relations

        weight = 100
        relations = {}
        for key in relation_data:
            relations[key] = {'weight': weight, 'consumes': relation_data[key]}
            weight -= 1

        return relations

    def build_sentries(self, relation_data=None):
        pass
