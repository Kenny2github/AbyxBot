import discord
from discord.ext import slash
from ..i18n import Context
from .protocol.lobby import Lobby
from .protocol.main_cog import add_game

class DummyLobby(Lobby):
    name = 'dummy-game'
    wait_time = 20
    min_players = 1
    max_players = 2
    max_spectators = 1

class DummyGame:

    name = 'dummygame'
    lobby: DummyLobby

    def __init__(self) -> None:
        self.lobby = DummyLobby(self.game_callback)

    async def game_callback(self, players: set[Context],
                            spectators: set[Context]) -> None:
        """Play the game"""
        await list(players)[0].webhook.send(f'Players: {players}; Spectators: {spectators}')

def setup(bot: slash.SlashBot):
    add_game(DummyGame())