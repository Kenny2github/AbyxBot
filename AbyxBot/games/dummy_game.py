# stdlib
from itertools import chain
import asyncio

# 3rd-party
import discord

# 1st-party
from .protocol.lobby import GameProperties, LobbyPlayers
from .protocol.main_cog import add_game

class DummyGameView(discord.ui.View):

    viewer: discord.abc.User
    players: LobbyPlayers
    spectators: LobbyPlayers

    def __init__(self, *, viewer: discord.abc.User, players: LobbyPlayers,
                 spectators: LobbyPlayers) -> None:
        super().__init__(timeout=None)
        self.viewer = viewer
        self.players = players
        self.spectators = spectators
        asyncio.create_task(self.game_callback())

    async def game_callback(self) -> None:
        """Play the game"""
        players = '\n'.join(player.mention for player in self.players.keys())
        spectators = '\n'.join(spectator.mention for spectator in self.spectators.keys())
        if self.viewer in self.players:
            msg = self.players[self.viewer]
        elif self.viewer in self.spectators:
            msg = self.spectators[self.viewer]
        else:
            raise RuntimeError(f'Unreachable - viewer: {self.viewer}, '
                               f'players: {self.players}, '
                               f'spectators: {self.spectators}')
        await msg.edit(content=None, embed=discord.Embed(
            description=f'Players:\n{players}\n'
            f'\nSpectators:\n{spectators}\n'
            f'\nViewer: {self.viewer.mention}'))

class DummyGame(GameProperties):

    name: str = 'dummygame'
    wait_time: int = 20
    min_players: int = 2
    max_players: int = 3
    max_spectators: int = 0

    def __init__(self, *, players: LobbyPlayers, spectators: LobbyPlayers) -> None:
        for viewer in chain(players.keys(), spectators.keys()):
            DummyGameView(viewer=viewer, players=players, spectators=spectators)

def setup(bot: discord.Client):
    add_game(DummyGame)
