from discord.ext.slash import SlashBot, cmd
from .i18n import Context

class Miscellaneous:
    """Miscellaneous commands with no clear thread."""

    @cmd()
    async def hello(self, ctx: Context):
        """Test whether the bot is running! Simply says "Hello World!"."""
        await ctx.respond(ctx.msg('hello'), ephemeral=True)

    @cmd()
    async def hmmst(self, ctx: Context):
        """hmmst"""
        await ctx.respond(ctx.msg('hmmst'))

def setup(bot: SlashBot):
    bot.add_slash_cog(Miscellaneous())
