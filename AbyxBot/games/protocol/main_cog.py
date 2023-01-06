# stdlib
from typing import Optional

# 3rd-party
import discord
from discord import app_commands
import discord.ext.commands as commands
from discord.app_commands import locale_str as _

# 1st-party
from ...i18n import Msg, error_embed
from .lobby import LobbyView, GameProperties

games: dict[str, type[GameProperties]] = {}

def add_game(game: type[GameProperties]) -> None:
    """Register the game view type to the game name."""
    games[game.name] = game

def setup(bot: commands.Bot):

    @app_commands.command()
    @app_commands.choices(
        game=[app_commands.Choice(name=_(key, key=f'games/{key}'), value=key)
              for key in games.keys()])
    @app_commands.describe(
        game='The game in question.',
        private='If True, view a private lobby with you as host. '
        'Overrides host if specified.',
        host='View the lobby hosted by this person.')
    async def game(ctx: discord.Interaction, game: str, private: bool = False,
                   host: Optional[discord.User] = None) -> None:
        """Get a view of the specified game lobby."""
        await ctx.response.defer(thinking=True)
        message = await ctx.original_response()
        if private:
            lobbier = ctx.user
        else:
            lobbier = host
        LobbyView(ctx.client, message, viewer=ctx.user,
                  game=games[game], host=lobbier)

    async def check_game(ctx: discord.Interaction) -> bool:
        if ctx.guild is None:
            return True # always allowed in DMs
        if games[ctx.namespace.game].dm_only:
            await ctx.response.send_message(embed=error_embed(
                ctx, Msg('lobby/dm-only-error')), ephemeral=True)
            return False
        return True

    game.add_check(check_game)
    bot.tree.add_command(game)
