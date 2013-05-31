import os
import subprocess

from mock import patch, call, MagicMock
from testtools import TestCase
from contextlib import contextmanager

from amulet.parser import TestParser

class ParserTests(TestCase):
    def test_maps_test_file(self):
        
