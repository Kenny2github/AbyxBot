# stdlib
from functools import partial
from logging import getLogger

# 3rd-party
import discord
from discord import app_commands
from discord.ext import commands

# 1st-party
from .config import config

SIGNALLED_EXCS = (
    app_commands.BotMissingPermissions,
    app_commands.MissingPermissions,
    app_commands.CommandOnCooldown,
)
UNLOGGED_EXCS = (
    app_commands.CheckFailure,
    app_commands.CommandNotFound,
)

logger = getLogger(__name__)

class AbyxTree(app_commands.CommandTree):
    async def on_error(
        self, ctx: discord.Interaction, exc: Exception
    ) -> None:
        logger.error('Ignoring exception in command %s - %s: %s',
                    ctx.command, type(exc).__name__, exc)
        if isinstance(exc, SIGNALLED_EXCS):
            if ctx.response.is_done():
                method = ctx.followup.send
            else:
                method = partial(ctx.response.send_message, ephemeral=True)
            await method(embed=discord.Embed(
                title='Error',
                description=str(exc),
                color=0xff0000
            ))
            # await method(embed=ctx.error_embed(str(exc)))
            return
        if isinstance(exc, UNLOGGED_EXCS):
            return
        logger.error('', exc_info=exc)

    async def interaction_check(self, ctx: discord.Interaction) -> bool:
        logger.info('User %s\t(%18d) in channel %s\t(%18d) running /%s',
                    ctx.user, ctx.user.id, ctx.channel,
                    ctx.channel.id if ctx.channel else '(none)',
                    ctx.command.qualified_name if ctx.command else '(none)')
        return True

class AbyxBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix='/',
            help_command=None,
            intents=discord.Intents.all(),
            tree_cls=AbyxTree
        )

    async def setup_hook(self) -> None:
        if config.debug_guild:
            debug_guild = discord.Object(config.debug_guild)
            self.tree.copy_global_to(guild=debug_guild)
        else:
            debug_guild = None
        await self.tree.sync(guild=debug_guild)
        logger.info('Synced commands')

    async def on_ready(self) -> None:
        logger.info('Ready!')

bot = AbyxBot()
