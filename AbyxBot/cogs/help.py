from __future__ import annotations
# stdlib
from typing import TYPE_CHECKING

# 3rd-party
import discord
from discord import app_commands
from discord.app_commands import locale_str as _

# 1st-party
from ..i18n import Msg, mkembed
from ..lib.utils import similarity
if TYPE_CHECKING:
    from ..lib.client import AbyxBot

COMMANDS_WITH_HELP = {
    'help/convert',
    'help/units',
    'help/lang',
}

@app_commands.command()
@app_commands.describe(command=_('The name of the command to get help for.'))
async def help(ctx: discord.Interaction, command: str):
    """Get help for a command."""
    command = 'help/' + command
    key = max(COMMANDS_WITH_HELP, key=lambda k: similarity(k, command))
    await ctx.response.send_message(embed=mkembed(ctx,
        Msg('help/title', key.split('/', 1)[1]), Msg(key),
        color=discord.Color.blue()
    ))

def setup(bot: AbyxBot):
    bot.tree.add_command(help)
