# stdlib
from typing import Protocol

# 3rd-party
from discord.ext import slash

# 1st-party
from ...i18n import Context
from .lobby import Lobby

class GameClass(Protocol):
    name: str
    lobby: Lobby

lobbier_opt = slash.Option(
    'Join the queue started by this person, '
    'or start (and join) a queue in their name.',
    type=slash.ApplicationCommandOptionType.USER)

games: dict[str, GameClass] = {}

def add_game(game: GameClass) -> None:
    games[game.name] = game

def setup(bot: slash.SlashBot):
    game_opt = slash.Option(
        'The game to join.',
        choices=games.keys())

    @bot.slash_cmd()
    async def join(ctx: Context, game: game_opt,
                   lobbier: lobbier_opt = None) -> None:
        """Join the queue for a game!"""
        await games[game].lobby.join(ctx, lobbier)

    @bot.slash_cmd()
    async def spectate(ctx: Context, game: game_opt,
                       lobbier: lobbier_opt = None) -> None:
        """Spectate a game."""
        await games[game].lobby.spectate(ctx, lobbier)

    @bot.slash_cmd()
    async def leave(ctx: Context, game: game_opt) -> None:
        """Leave the queue for a game."""
        await games[game].lobby.leave(ctx)