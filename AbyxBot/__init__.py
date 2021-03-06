# stdlib
import importlib
import asyncio

# 3rd-party
from discord.ext import slash

# 1st-party
from .client import client
from .config import TOKEN, cmdargs
from .db import db
from .logger import get_logger
from .status import SetStatus
from .watcher import stop_on_change

MODULES = {
    '2048': ('games.twozerofoureight', '2048'),
    'Help': ('help', 'help'),
    'Internationalization': ('i18n', 'i18n'),
    'Miscellaneous Commands': ('misc_cmds', 'misc'),
    'Numguess': ('games.numguess', 'numguess'),
    'Sudo Commands': ('sudo', 'sudo'),
    'Translation': ('translation', 'trans'),
    'Unit Conversions': ('units', 'units'),
    'Lexical Analysis': ('words', 'words'),
}

logger = get_logger('init')

def import_cog(bot: slash.SlashBot, name: str, fname: str):
    """Load a module and run its setup function."""
    module = importlib.import_module('.' + fname, __name__)
    if asyncio.iscoroutinefunction(module.setup):
        bot.loop.run_until_complete(module.setup(bot))
    else:
        module.setup(bot)
    logger.info('Loaded %s', name)

globs = {}

def run():
    """Run the bot."""
    client.loop.run_until_complete(db.init())
    for name, (fname, cmdname) in MODULES.items():
        if cmdname in cmdargs.disable:
            logger.info('Not loading %s', name)
        else:
            import_cog(client, name, fname)
    globs['status'] = SetStatus(client)
    globs['wakeup'] = client.loop.create_task(stop_on_change(client, 'AbyxBot'))
    globs['status'].start()
    client.loop.run_until_complete(client.start(TOKEN))

async def cleanup_tasks():
    for task in asyncio.all_tasks():
        try:
            await asyncio.wait_for(task, 3.0)
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            return

def done():
    """Cleanup and shutdown the bot."""
    try:
        if 'wakeup' in globs:
            globs['wakeup'].cancel()
        if 'status' in globs:
            globs['status'].cancel()
    except RuntimeError as exc:
        print(exc)
    client.loop.run_until_complete(client.close())
    if db.conn is not None:
        client.loop.run_until_complete(db.stop())
    client.loop.run_until_complete(cleanup_tasks())
    client.loop.stop()
    client.loop.close()
