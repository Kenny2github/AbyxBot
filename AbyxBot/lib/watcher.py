# stdlib
import os
from logging import getLogger
import asyncio

# 3rd-party
from discord.ext import commands

# 1st-party
from .utils import recurse_mtimes

logger = getLogger(__name__)

async def stop_on_change(bot: commands.Bot, path: str):
    mtimes = recurse_mtimes(path)
    while 1:
        for fn, mtime in mtimes.items():
            try:
                newmtime = os.path.getmtime(fn)
            except FileNotFoundError:
                logger.info("File '%s' deleted, closing client", fn)
                await bot.close()
                return
            if newmtime > mtime:
                logger.info("File '%s' modified, closing client", fn)
                await bot.close()
                return
        await asyncio.sleep(1)
