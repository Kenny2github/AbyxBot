from functools import partial
import discord
from discord.ext import commands, slash
from .config import config
from .i18n import Context
from .logger import get_logger

SIGNALLED_EXCS = (
    commands.BotMissingPermissions,
    commands.MissingPermissions,
    commands.MissingRequiredArgument,
    commands.BadArgument,
    commands.CommandOnCooldown,
)
UNLOGGED_EXCS = (
    commands.CheckFailure,
    commands.CommandNotFound,
    commands.TooManyArguments
)

logger = get_logger('client')
cmd_logger = get_logger('cmds')

client = slash.SlashBot(
    command_prefix='/',
    help_command=None,
    intents=discord.Intents.all(),
    debug_guild=config.get('debug_guild'),
    fetch_if_not_get=True
)

@client.event
async def on_command_error(ctx: Context, exc: Exception):
    logger.error('Ignoring exception in command %s - %s: %s',
                 ctx.command, type(exc).__name__, exc)
    if isinstance(exc, SIGNALLED_EXCS):
        if ctx.webhook is None:
            method = partial(ctx.respond, ephemeral=True)
        else:
            method = ctx.webhook.send
        await method(embed=ctx.embed(
            'error', str(exc), color=0xff0000))
        return
    if isinstance(exc, UNLOGGED_EXCS):
        return
    logger.error('', exc_info=exc)

@client.event
async def on_before_slash_command_invoke(ctx: Context):
    cmd_logger.info(ctx)

@client.event
async def on_ready():
    logger.info('Ready!')
