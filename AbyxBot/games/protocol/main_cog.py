# stdlib
from typing import Optional

# 3rd-party
import discord
from discord import app_commands
import discord.ext.commands as commands
from discord.app_commands import locale_str as _

# 1st-party
from .lobby import LobbyView, GameView

games: dict[str, type[GameView]] = {}

def add_game(game: type[GameView]) -> None:
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
        LobbyView(message, viewer=ctx.user,
                  game=games[game], host=lobbier)

    bot.tree.add_command(game)
