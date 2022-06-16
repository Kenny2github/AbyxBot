# stdlib
import importlib
import asyncio
from logging import getLogger

# 3rd-party
from discord.ext import slash

# 1st-party
from .client import client
from .config import TOKEN, cmdargs
from .database import db
from .logs import activate as activate_logging
from .status import SetStatus
from .watcher import stop_on_change

MODULES = {
    # '2048': ('games.twozerofoureight', '2048'),
    # 'Help': ('help', 'help'),
    # 'Internationalization': ('i18n', 'i18n'),
    'Miscellaneous Commands': ('misc_cmds', 'misc'),
    # 'Numguess': ('games.numguess', 'numguess'),
    # 'Sudo Commands': ('sudo', 'sudo'),
    # 'Translation': ('translation', 'trans'),
    # 'Unit Conversions': ('units', 'units'),
    # 'Lexical Analysis': ('words', 'words'),
    # 'Dummy Game': ('games.dummy_game', 'dummy_game'),
    # # NOTE: This must come after all game entries
    # 'Games': ('games.protocol.main_cog', 'games'),
}

logger = getLogger(__name__)

async def import_cog(bot: slash.SlashBot, name: str, fname: str):
    """Load a module and run its setup function."""
    module = importlib.import_module('.' + fname, __name__)
    if asyncio.iscoroutinefunction(module.setup):
        await module.setup(bot)
    else:
        module.setup(bot)
    logger.info('Loaded %s', name)

globs: dict[str, asyncio.Task] = {}

async def run():
    """Run the bot."""
    await db.init()
    for name, (fname, cmdname) in MODULES.items():
        if cmdname in cmdargs.disable:
            logger.info('Not loading %s', name)
        else:
            await import_cog(client, name, fname)
    globs['status'] = SetStatus(client)
    globs['wakeup'] = asyncio.create_task(stop_on_change(client, 'AbyxBot'))
    globs['logger'] = activate_logging()
    globs['status'].start()
    await client.start(TOKEN)

async def cleanup_tasks():
    for task in asyncio.all_tasks():
        try:
            # note that this cancels the task on timeout
            await asyncio.wait_for(task, 3.0)
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            return

async def done():
    """Cleanup and shutdown the bot."""
    try:
        if 'wakeup' in globs:
            globs['wakeup'].cancel()
        if 'status' in globs:
            globs['status'].cancel()
        if 'logger' in globs:
            globs['logger'].cancel()
    except RuntimeError as exc:
        print(exc)
    await client.close()
    if db.conn is not None:
        await db.stop()
    await cleanup_tasks()
