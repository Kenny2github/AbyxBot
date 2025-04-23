from __future__ import annotations
# stdlib
import asyncio
import json
from typing import TYPE_CHECKING, Callable, Optional
import unicodedata

# 3rd-party
import discord
from discord.ext import commands
from discord import app_commands

# 1st-party
from ..consts.config import config
from ..i18n import mkmsg, mkembed, error_embed, Msg
if TYPE_CHECKING:
    from ..lib.client import AbyxBot

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
    await ctx.edit_original_response(embed=mkembed(ctx,
        Msg('misc/purge-title'), Msg('misc/purge', deleted),
        color=discord.Color.red()
    ))
    await asyncio.sleep(2)

@app_commands.context_menu(name='Purge after this')
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.checks.bot_has_permissions(manage_messages=True)
async def purge_after(ctx: discord.Interaction, msg: discord.Message):
    if not isinstance(ctx.channel, discord.abc.Messageable):
        return
    if isinstance(ctx.channel, discord.PartialMessageable):
        return
    await ctx.response.defer(ephemeral=True)
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
        latency = f'{ctx.client.latency * 1000:.0f}'
        await ctx.response.send_message(embed=mkembed(ctx,
            Msg('misc/pong-title'), Msg('misc/pong-ms', latency)
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
        if not isinstance(ctx.channel, discord.abc.Messageable):
            return
        if isinstance(ctx.channel, discord.PartialMessageable):
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
                         discord.utils.escape_markdown(char), f'{num:>04x}')
        msg = '\n'.join(map(to_string, chars))
        msg = mkmsg(ctx, 'misc/charinfo-start') + '\n' + msg
        await ctx.response.send_message(embed=mkembed(ctx,
            Msg('misc/charinfo-title'), msg[:2000]
        ))

    @app_commands.command()
    async def info(self, ctx: discord.Interaction):
        """Get information about the bot."""
        ainfo = ctx.client.application
        assert ainfo is not None
        assert ainfo.icon is not None
        invite = discord.utils.oauth_url(
            ainfo.id,
            permissions=discord.Permissions(
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
                external_emojis=True,
                add_reactions=True,
            ),
            scopes=['bot', 'applications.commands'],
        )
        embed = mkembed(
            ctx, title=str(ctx.client.user),
            description=ainfo.description,
            fields=(
                (Msg('misc/info-id'), ainfo.id, True),
                (Msg('misc/info-owner'), str(ainfo.owner), True),
                (Msg('misc/info-config-title'),
                 Msg('misc/info-config', config.web_root), True),
                (Msg('misc/info-invite-title'),
                 Msg('misc/info-invite', invite), True),
            )
        )
        embed.set_thumbnail(url=ainfo.icon.url)
        await ctx.response.send_message(embed=embed)

async def setup(bot: AbyxBot):
    await bot.add_cog(Miscellaneous())
    bot.tree.add_command(purge_after)
