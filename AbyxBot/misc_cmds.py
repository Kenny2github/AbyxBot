from discord.ext.slash import SlashBot, cmd
from .i18n import Context, Msg

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

    @cmd()
    async def ping(self, ctx: Context):
        """Pong! Get bot latency in milliseconds."""
        await ctx.respond(embed=ctx.embed(
            Msg('misc/pong-title'), Msg('misc/pong-ms', ctx.bot.latency * 1000)
        ))

def setup(bot: SlashBot):
    bot.add_slash_cog(Miscellaneous())
