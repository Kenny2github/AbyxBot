# stdlib
import sys
import os
import argparse
import json
import logging
from typing import NamedTuple, Optional

# 1st-party
from .utils import AttrDict

class Config(NamedTuple):
    token: str
    client_id: int
    client_secret: str
    web_root: str
    gcloud_project_id: str
    gcloud_auth_json: str
    file_root: Optional[str] = None
    debug_guild: Optional[int] = None

with open('config.json') as f:
    config = Config(**json.load(f))

parser = argparse.ArgumentParser(description='Run AbyxBot.')
parser.add_argument('-d', '--disable', nargs='*', metavar='disable',
                    default=[], help='modules not to run')
parser.add_argument('--stdout', action='store_true', default=False,
                    help='log to stdout instead of a file')
parser.add_argument('-v', '--verbose', action='store_const', dest='level',
                    const=logging.DEBUG, default=logging.INFO,
                    help='emit debug logging messages')

runner = os.path.basename(sys.argv[0])
if runner == '_check.py':
    # dummy cmdargs for the i18n audit script
    cmdargs = AttrDict({'disable': [], 'stdout': True, 'level': logging.INFO})
else:
    cmdargs = parser.parse_args()
del runner

TOKEN: str = config.token
