# stdlib
import sys
import os
import time
import logging
from logging.handlers import QueueHandler
import asyncio

# 1st-party
from .config import cmdargs

FORMAT = '{levelname}\t{asctime} {name:20}{message}'
TIME = '%Y-%m-%d'

os.makedirs('logs', exist_ok=True)

def activate():
    queue = asyncio.Queue()
    handler = QueueHandler(queue)
    handler.setFormatter(logging.Formatter(FORMAT, style='{'))
    logging.basicConfig(handlers=[handler], level=logging.WARNING)
    logging.getLogger('AbyxBot').setLevel(cmdargs.level)
    logging.getLogger('discord').setLevel(logging.INFO)
    return asyncio.create_task(consume_logs(queue))

async def consume_logs(queue: asyncio.Queue):
    if cmdargs.stdout:
        handler = logging.StreamHandler(sys.stdout)
    else:
        handler = logging.FileHandler(
            'logs/%s.log' % time.strftime(TIME), 'a', 'utf8')
    while 1: # the nice thing about tasks is that they can be cancelled
        record: logging.LogRecord = await queue.get()
        handler.emit(record)
