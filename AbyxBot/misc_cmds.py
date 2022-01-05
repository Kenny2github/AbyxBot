# stdlib
import asyncio
import json
import unicodedata

# 3rd-party
import discord
from discord.ext import commands
from discord.ext.slash import ApplicationCommandOptionType, Option, SlashBot, cmd

# 1st-party
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

    @cmd()
    async def purge(self, ctx: Context, after: Option(
        description='Purge all messages coming after this message ID.'
    ) = None, limit: Option(
        description='Purge (at most) this many messages into the past.',
        min_value=1
    ) = 100, user: Option(
        description='Only purge messages from this user.',
        type=ApplicationCommandOptionType.USER
    ) = None, matches: Option(
        description='Only purge messages that contain this substring.'
    ) = None):
        """Purge messages. See descriptions of the `after` and `limit` parameters."""
        if not (ctx.channel.permissions_for(ctx.author).manage_messages
                and ctx.channel.permissions_for(ctx.me).manage_messages):
            await ctx.respond(embed=ctx.error_embed(
                Msg('misc/purge-perms')), ephemeral=True)
            return
        def check_msg(msg: discord.Message) -> bool:
            if user is not None:
                if msg.author.id != user.id:
                    return False
            if matches is not None:
                if matches not in msg.content:
                    return False
            return True
        if after is not None:
            deleted = len(await ctx.channel.purge(
                after=discord.Object(int(after)), check=check_msg))
        elif limit is not None:
            deleted = len(await ctx.channel.purge(
                limit=limit, check=check_msg))
        else:
            deleted = 0
        await ctx.respond(embed=ctx.embed(
            Msg('misc/purge-title'), Msg('misc/purge', deleted),
            color=discord.Color.red()
        ))
        await asyncio.sleep(2)
        await ctx.delete()

    @cmd()
    async def charinfo(self, ctx: Context, chars: Option('The characters.')):
        """Get information about a sequence of characters."""
        chars: str = chars
        if '\\' in chars:
            try:
                chars = chars.encode().decode('unicode-escape')
            except UnicodeDecodeError:
                pass # use original string
        def to_string(char: str) -> str:
            digit = f'{ord(char):>08x}'
            name = unicodedata.name(char, ctx.msg('misc/charname-not-found'))
            return ctx.msg('misc/charinfo', digit, name, char,
                           json.dumps(char).strip('"'))
        msg = '\n'.join(map(to_string, chars))
        msg = ctx.msg('misc/charinfo-start') + '\n' + msg
        await ctx.respond(embed=ctx.embed(
            Msg('misc/charinfo-title'), msg[:2000]
        ))

def setup(bot: SlashBot):
    bot.add_slash_cog(Miscellaneous())
