import argparse
import json
import logging
from AbyxBot.utils import AttrDict

with open('config.json') as f:
    config = AttrDict(json.load(f))

parser = argparse.ArgumentParser(description='Run AbyxBot.')
parser.add_argument('-d', '--disable', nargs='*', metavar='disable',
                    default=[], help='modules not to run')
parser.add_argument('--stdout', action='store_true', default=False,
                    help='log to stdout instead of a file')
parser.add_argument('-v', '--verbose', action='store_const', dest='level',
                    const=logging.DEBUG, default=logging.INFO,
                    help='emit debug logging messages')
cmdargs = parser.parse_args()

TOKEN: str = config.token