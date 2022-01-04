import discord
from discord.ext.slash import Option, SlashBot, cmd
from .i18n import Context, Msg
from .utils import similarity

COMMANDS_WITH_HELP = {
    'help/convert',
    'help/units',
    'help/lang',
}

@cmd()
async def help(ctx: Context, command: Option(
    description='The name of the command to get help for.'
)):
    """Get help for a command."""
    key = max(COMMANDS_WITH_HELP, key=lambda k: similarity(k, command))
    await ctx.respond(embed=ctx.embed(
        Msg('help/title', key), Msg(key),
        color=discord.Color.blue()
    ))

def setup(bot: SlashBot):
    bot.slash.add(help)