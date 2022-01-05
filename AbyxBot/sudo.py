import asyncio
from discord.ext.slash import SlashBot, group
from .i18n import Context, Msg
from .utils import asyncify

@group(default_permission=False)
async def sudo(ctx: Context):
    """Commands available only to the bot owner."""

@sudo.slash_cmd()
async def stop(ctx: Context):
    """Stop the bot."""
    await ctx.respond(ctx.msg('sudo/stop'), ephemeral=True)
    await ctx.bot.close()

@sudo.slash_cmd()
async def r25n(ctx: Context):
    """Reload i18n strings immediately."""
    asyncio.create_task(asyncify(Msg.load_strings))
    await ctx.respond(ctx.msg('sudo/r25n'), ephemeral=True)

def setup(bot: SlashBot):
    bot.slash.add(sudo)
    async def on_slash_permissions():
        sudo.add_perm(bot.app_info.owner, True, None)
        await bot.register_permissions()
    bot.event(on_slash_permissions)
