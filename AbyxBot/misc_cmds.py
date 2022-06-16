# stdlib
import asyncio
import json
from typing import Callable, Optional
import unicodedata

# 3rd-party
import discord
from discord.ext import commands
from discord import app_commands

# 1st-party
from .type_hints import HistoriedChannel
from .i18n import mkmsg, mkembed, error_embed, Msg

def check_msg(user: Optional[discord.User] = None,
              matches: Optional[str] = None
              ) -> Callable[[discord.Message], bool]:
    def _check(msg: discord.Message) -> bool:
        if user is not None:
            if msg.author.id != user.id:
                return False
        if matches is not None:
            if matches not in msg.content:
                return False
        return True
    return _check

async def post_purge(ctx: discord.Interaction, deleted: int) -> None:
    await ctx.response.send_message(embed=mkembed(ctx,
        Msg('misc/purge-title'), Msg('misc/purge', deleted),
        color=discord.Color.red()
    ))
    await asyncio.sleep(2)
    await ctx.delete_original_message()

@app_commands.context_menu(name='Purge after this')
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.checks.bot_has_permissions(manage_messages=True)
async def purge_after(ctx: discord.Interaction, msg: discord.Message):
    if not isinstance(ctx.channel, HistoriedChannel):
        return
    deleted = len(await ctx.channel.purge(after=msg))
    await post_purge(ctx, deleted)

@purge_after.error
async def purge_error(ctx: discord.Interaction,
                      exc: app_commands.AppCommandError) -> None:
    if not isinstance(exc, (app_commands.MissingPermissions,
                            app_commands.BotMissingPermissions)):
        raise exc
    await ctx.response.send_message(embed=error_embed(ctx,
            Msg('misc/purge-perms')), ephemeral=True)

class Miscellaneous(commands.Cog):
    """Miscellaneous commands with no clear thread."""

    @app_commands.command()
    async def hello(self, ctx: discord.Interaction):
        """Test whether the bot is running! Simply says "Hello World!"."""
        await ctx.response.send_message(mkmsg(ctx, 'hello'), ephemeral=True)

    @app_commands.command()
    async def hmmst(self, ctx: discord.Interaction):
        """hmmst"""
        await ctx.response.send_message(mkmsg(ctx, 'hmmst'))

    @app_commands.command()
    async def ping(self, ctx: discord.Interaction):
        """Pong! Get bot latency in milliseconds."""
        await ctx.response.send_message(embed=mkembed(ctx,
            Msg('misc/pong-title'), Msg('misc/pong-ms', ctx.client.latency * 1000)
        ))

    @app_commands.command()
    @app_commands.describe(
        limit='Purge (at most) this many messages into the past.',
        user='Only purge messages from this user.',
        matches='Only purge messages that contain this substring.'
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def purge(self, ctx: discord.Interaction, after: Optional[int] = None,
                    limit: app_commands.Range[int, 1] = 100,
                    user: Optional[discord.User] = None,
                    matches: Optional[str] = None):
        """Purge messages. See descriptions of the `after` and `limit` parameters."""
        if not isinstance(ctx.channel, HistoriedChannel):
            return
        def check_msg(msg: discord.Message) -> bool:
            if user is not None:
                if msg.author.id != user.id:
                    return False
            if matches is not None:
                if matches not in msg.content:
                    return False
            return True
        deleted = len(await ctx.channel.purge(
            limit=limit, check=check_msg))
        await post_purge(ctx, deleted)

    purge.error(purge_error)

    @app_commands.command()
    @app_commands.describe(chars='The characters')
    async def charinfo(self, ctx: discord.Interaction, chars: str):
        """Get information about a sequence of characters."""
        if '\\' in chars:
            try:
                chars = chars.encode().decode('unicode-escape')
            except UnicodeDecodeError:
                pass # use original string
        def to_string(char: str) -> str:
            num = ord(char)
            py_escape = fr'\U{num:>08x}'
            json_escape = json.dumps(char).strip('"')
            name = unicodedata.name(char, mkmsg(ctx, 'misc/charname-not-found'))
            return mkmsg(ctx, 'misc/charinfo', py_escape, json_escape, name,
                         discord.utils.escape_markdown(char), num)
        msg = '\n'.join(map(to_string, chars))
        msg = mkmsg(ctx, 'misc/charinfo-start') + '\n' + msg
        await ctx.response.send_message(embed=mkembed(ctx,
            Msg('misc/charinfo-title'), msg[:2000]
        ))

async def setup(bot: commands.Bot):
    await bot.add_cog(Miscellaneous())
    bot.tree.add_command(purge_after)
