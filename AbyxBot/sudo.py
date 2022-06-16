# stdlib
import asyncio

# 3rd-party
import discord
from discord.ext import commands
from discord import app_commands

# 1st-party
from .i18n import Msg, error_embed, mkmsg
from .utils import asyncify

@app_commands.default_permissions()
class Sudo(app_commands.Group):
    """Commands available only to the bot owner."""

    def interaction_check(self, ctx: discord.Interaction) -> bool:
        assert ctx.client.application is not None
        if ctx.user.id == ctx.client.application.owner.id:
            return True
        asyncio.create_task(ctx.response.send_message(
            embed=error_embed(ctx, Msg('sudo/cant')), ephemeral=True))
        return False

    @app_commands.command()
    async def stop(self, ctx: discord.Interaction):
        """Stop the bot."""
        await ctx.response.send_message(
            mkmsg(ctx, 'sudo/stop'), ephemeral=True)
        await ctx.client.close()

    @app_commands.command()
    async def r25n(self, ctx: discord.Interaction):
        """Reload i18n strings immediately."""
        asyncio.create_task(asyncify(Msg.load_strings))
        await ctx.response.send_message(
            mkmsg(ctx, 'sudo/r25n'), ephemeral=True)

    @app_commands.command()
    async def sync(self, ctx: discord.Interaction):
        """Sync global commands. Run after deploying a bot version.

        NOTE: Never change the signature for this command.
        """
        bot: commands.Bot = ctx.client # type: ignore - I know it is
        await bot.tree.sync()
        await ctx.response.send_message(
            mkmsg(ctx, 'sudo/sync'), ephemeral=True)

def setup(bot: commands.Bot):
    bot.tree.add_command(Sudo())
