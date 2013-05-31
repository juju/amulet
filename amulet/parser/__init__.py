"""Test script parser"""

import os
import sys

import plugins

class TestParser:
    """Test Parser class"""
    instructions = {}
    def __init__(self, test_file=None):
        if test_file:
            self.parse(test_file)

    def parse(file):
        with open(file) as f:
            for line in f:
                line = line.strip()
                try:
                    cmd, opts = _parse_line(line)
                except ParseError:
                    raise
                else:
                    queue(cmd, options)

    def queue(command, options):
        

    def _parse_line(line):
        cmd, options = line.split(' ', 1)
        if not hasattr(commands, cmd):
            raise ParseError('%s is not a valid command' % cmd)

        yield cmd, options
