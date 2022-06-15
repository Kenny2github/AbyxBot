# stdlib
from functools import partial
from logging import getLogger

# 3rd-party
import discord
from discord.ext import commands, slash

# 1st-party
from .config import config
from .i18n import Context

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

logger = getLogger(__name__)

client = slash.SlashBot(
    command_prefix='/',
    help_command=None,
    intents=discord.Intents.all(),
    debug_guild=config.debug_guild,
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
        await method(embed=ctx.error_embed(str(exc)))
        return
    if isinstance(exc, UNLOGGED_EXCS):
        return
    logger.error('', exc_info=exc)

@client.event
async def on_before_slash_command_invoke(ctx: Context):
    logger.info('User %s\t(%18d) in channel %s\t(%18d) running /%s',
                ctx.author, ctx.author.id, ctx.channel,
                ctx.channel.id, ctx.command)

@client.event
async def on_ready():
    logger.info('Ready!')
