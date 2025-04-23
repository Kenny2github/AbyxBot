from __future__ import annotations
# stdlib
import re
from io import StringIO
from contextlib import redirect_stdout
import traceback
import asyncio
from typing import TYPE_CHECKING, Any, Awaitable, Callable, cast

# 3rd-party
import discord
from discord.ext import commands
from discord import app_commands

# 1st-party
from ..i18n import Msg, error_embed, mkmsg
from ..lib.utils import asyncify
if TYPE_CHECKING:
    from ..lib.client import AbyxBot

# eval-related stuff

def _init_env(ctx: discord.Interaction) -> tuple[dict[str, Any], StringIO]:
    def exit(*args):
        raise SystemExit(*args)
    env = {
        'asyncio': asyncio,
        'ctx': ctx,
        'commands': commands,
        'discord': discord,
        'exit': exit,
    }
    out = StringIO()
    return env, out

def _func_from_arg(arg: str, env: dict[str, Any]
                   ) -> tuple[str, Callable[[], Awaitable[Any]]]:
    lines = arg.strip('`').rstrip().lstrip('\n').splitlines()
    indent = '    '
    for line in lines:
        strp = line.lstrip()
        if strp != line:
            indent = line[:len(line) - len(strp)]
            break
    lines = ''.join(indent * 2 + line + '\n' for line in lines)
    globline = ', '.join(i for i in env.keys() if i not in {
        'func', 'asyncio', 'commands', 'discord', 'exit'
    })
    lines = f'''{indent}try:
{indent*2}global {globline}
{lines}
{indent}finally:
{indent*2}globals().update(locals())'''
    lines = f"async def func():\n{lines}"
    exec(lines, env)
    return lines, env['func']

def _trace():
    return re.sub(r'(?i)".*?abyxbot[\\/]', '"', traceback.format_exc())

class EvalModal(discord.ui.Modal):

    def __init__(self, ctx: discord.Interaction) -> None:
        super().__init__(title=mkmsg(ctx, 'sudo/eval-title'))
        self.text = discord.ui.TextInput(
            label=mkmsg(ctx, 'sudo/code-label'),
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.text)

    async def on_submit(self, ctx: discord.Interaction) -> None:
        await ctx.response.defer(thinking=True)
        env, out = _init_env(ctx)
        text, func = _func_from_arg(self.text.value, env)
        kwargs = {}
        try:
            with redirect_stdout(out):
                ret = await func()
        except SystemExit:
            pass
        except BaseException:
            trace = _trace()
            kwargs['embed'] = error_embed(
                ctx, f'```\n{trace}\n```\n`func`:```\n{text}\n```')
        else:
            kwargs['embed'] = discord.Embed(
                title=mkmsg(ctx, 'success'),
                description=f'```{ret!r}```',
                color=discord.Color.blue())
        kwargs['content'] = f'```\n{out.getvalue()}\n```'
        await ctx.edit_original_response(**kwargs)

# actual cog

@app_commands.default_permissions()
class Sudo(app_commands.Group):
    """Commands available only to the bot owner."""

    def interaction_check(self, ctx: discord.Interaction) -> bool:
        assert ctx.client.application is not None
        if ctx.user.id == ctx.client.application.owner.id:
            return True
        asyncio.create_task(ctx.response.send_message(
            embed=error_embed(ctx, Msg('sudo/cant')), ephemeral=True))
        return False

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

    @app_commands.command()
    async def sync(self, ctx: discord.Interaction):
        """Sync global commands. Run after deploying a bot version.

        NOTE: Never change the signature for this command.
        """
        bot = cast(commands.Bot, ctx.client)
        await bot.tree.sync()
        await ctx.response.send_message(
            mkmsg(ctx, 'sudo/sync'), ephemeral=True)

    @app_commands.command()
    async def eval(self, ctx: discord.Interaction):
        """Evaluate arbitrary code."""
        await ctx.response.send_modal(EvalModal(ctx))

def setup(bot: AbyxBot):
    bot.tree.add_command(Sudo())
