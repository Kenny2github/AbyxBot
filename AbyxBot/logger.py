import sys
import os
import time
import logging
import asyncio
from typing import Callable
from discord.ext import slash
from .config import cmdargs

FORMAT = '{levelname}\t{asctime} {name:20}{message}'
TIME = '%Y-%m-%d'

os.makedirs('logs', exist_ok=True)

# asyncify some logging classes

class AsyncEmitter:
    """Provides an overriding method that calls emit() in a task."""

    super_emit: Callable

    async def aemit(self, record) -> None:
        await asyncio.get_event_loop().run_in_executor(
            None, self.super_emit, record)

    def emit(self, record) -> None:
        asyncio.get_event_loop().create_task(self.aemit(record))

class AsyncStreamHandler(AsyncEmitter, logging.StreamHandler):
    super_emit = logging.StreamHandler.emit

class AsyncFileHandler(AsyncEmitter, logging.FileHandler):
    super_emit = logging.FileHandler.emit

class CtxLogger(logging.Logger):
    """Wrapper around Logger with context-handling magic."""

    def _log(
        self, level, msg, args, exc_info=None, extra=None,
        stack_info=False, stacklevel=1
    ) -> None:
        if isinstance(msg, slash.Context):
            assert not args
            args = (msg.author, msg.author.id, msg.channel,
                    msg.channel.id, msg.command)
            msg = 'User %s\t(%18d) in channel %s\t(%18d) running /%s'
        return super()._log(
            level, msg, args, exc_info=exc_info, extra=extra,
            stack_info=stack_info, stacklevel=stacklevel)

if cmdargs.stdout:
    handler = AsyncStreamHandler(sys.stdout)
else:
    handler = AsyncFileHandler(
        'logs/%s.log' % time.strftime(TIME), 'a', 'utf8')
handler.setFormatter(logging.Formatter(FORMAT, style="{"))
discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.WARNING)
discord_logger.addHandler(handler)
slash_logger = logging.getLogger('discord.ext.slash')
slash_logger.setLevel(cmdargs.level)

def get_logger(name: str) -> CtxLogger:
    """Get an asynchronous logger for your module."""
    logger = CtxLogger('AbyxBot.' + name, level=cmdargs.level)
    logger.addHandler(handler)
    return logger
