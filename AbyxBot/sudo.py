# stdlib
import asyncio

# 3rd-party
import discord
from discord.ext import commands
from discord import app_commands

# 1st-party
from .i18n import Msg, mkmsg
from .utils import asyncify

@app_commands.default_permissions()
class Sudo(app_commands.Group):
    """Commands available only to the bot owner."""

    def interaction_check(self, interaction: discord.Interaction) -> bool:
        assert interaction.client.application is not None
        return interaction.user.id == interaction.client.application.owner.id

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

def setup(bot: commands.Bot):
    bot.tree.add_command(Sudo())
