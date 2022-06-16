# stdlib
import asyncio
import json
import unicodedata

# 3rd-party
import discord
from discord.ext import commands
from discord import app_commands

# 1st-party
from .i18n import mkmsg, mkembed, Msg

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

    # @app_commands.command()
    # async def purge(self, ctx: discord.Interaction, after: Option(
    #     description='Purge all messages coming after this message ID.'
    # ) = None, limit: Option(
    #     description='Purge (at most) this many messages into the past.',
    #     min_value=1
    # ) = 100, user: Option(
    #     description='Only purge messages from this user.',
    #     type=ApplicationCommandOptionType.USER
    # ) = None, matches: Option(
    #     description='Only purge messages that contain this substring.'
    # ) = None):
    #     """Purge messages. See descriptions of the `after` and `limit` parameters."""
    #     if not (ctx.channel.permissions_for(ctx.author).manage_messages
    #             and ctx.channel.permissions_for(ctx.me).manage_messages):
    #         await ctx.respond(embed=ctx.error_embed(
    #             Msg('misc/purge-perms')), ephemeral=True)
    #         return
    #     def check_msg(msg: discord.Message) -> bool:
    #         if user is not None:
    #             if msg.author.id != user.id:
    #                 return False
    #         if matches is not None:
    #             if matches not in msg.content:
    #                 return False
    #         return True
    #     if after is not None:
    #         deleted = len(await ctx.channel.purge(
    #             after=discord.Object(int(after)), check=check_msg))
    #     elif limit is not None:
    #         deleted = len(await ctx.channel.purge(
    #             limit=limit, check=check_msg))
    #     else:
    #         deleted = 0
    #     await ctx.respond(embed=ctx.embed(
    #         Msg('misc/purge-title'), Msg('misc/purge', deleted),
    #         color=discord.Color.red()
    #     ))
    #     await asyncio.sleep(2)
    #     await ctx.delete()

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
