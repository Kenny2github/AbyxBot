import os
import asyncio
from discord.ext import commands
from .utils import recurse_mtimes
from .logger import get_logger

logger = get_logger('watcher')

async def stop_on_change(bot: commands.Bot, path: str):
    mtimes = recurse_mtimes(path)
    await bot.wait_until_ready()
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