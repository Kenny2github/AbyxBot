# stdlib
import importlib
import asyncio
from logging import getLogger
from typing import TypedDict

# 3rd-party
from discord.ext import commands

# 1st-party
from .consts.config import TOKEN, cmdargs
from .lib.client import bot
from .lib.database import db
from .lib.logs import activate as activate_logging
from .lib.status import SetStatus
from .lib.watcher import stop_on_change
from .server import Handler

MODULES = {
    '2048': ('games.twozerofoureight', '2048'),
    'Help': ('cogs.help', 'help'),
    'Internationalization': ('i18n', 'i18n'),
    'Miscellaneous Commands': ('cogs.misc_cmds', 'misc'),
    'Numguess': ('games.numguess', 'numguess'),
    'Sudo Commands': ('cogs.sudo', 'sudo'),
    'Translation': ('translation', 'trans'),
    'Unit Conversions': ('cogs.units', 'units'),
    'Lexical Analysis': ('cogs.words', 'words'),
    'Dictionaries': ('cogs.define', 'define'),
    'Dummy Game': ('games.dummy_game', 'dummy_game'),
    'Connect 4': ('games.connect4', 'connect4'),
    'Go Fish': ('games.card_games.go_fish', 'go_fish'),
    # NOTE: This must come after all game entries
    'Games': ('games.protocol.main_cog', 'games'),
}

logger = getLogger(__name__)

async def import_cog(bot: commands.Bot, name: str, fname: str):
    """Load a module and run its setup function."""
    module = importlib.import_module('.' + fname, __name__)
    if asyncio.iscoroutinefunction(module.setup):
        await module.setup(bot)
    else:
        module.setup(bot)
    logger.info('Loaded %s', name)

class Globs(TypedDict, total=False):
    logger: asyncio.Task[None]
    server: Handler
    status: SetStatus
    wakeup: asyncio.Task[None]

globs: Globs = {}

async def run():
    """Run the bot."""
    globs['logger'] = activate_logging() # NOTE: Do this first
    await db.init()
    globs['server'] = Handler(bot)
    for name, (fname, cmdname) in MODULES.items():
        if cmdname in cmdargs.disable:
            logger.info('Not loading %s', name)
        else:
            await import_cog(bot, name, fname)
    globs['status'] = SetStatus(bot)
    globs['wakeup'] = asyncio.create_task(stop_on_change(bot, 'AbyxBot'))
    await globs['server'].start()
    await bot.login(TOKEN)
    globs['status'].start()
    await bot.connect()

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
        if 'server' in globs:
            await globs['server'].stop()
        if 'wakeup' in globs:
            globs['wakeup'].cancel()
        if 'status' in globs:
            globs['status'].cancel()
        if 'logger' in globs:
            globs['logger'].cancel()
    except RuntimeError as exc:
        print(exc)
    await bot.close()
    if db.conn is not None:
        await db.stop()
    await cleanup_tasks()
