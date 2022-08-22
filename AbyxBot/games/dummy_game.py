# stdlib
from itertools import chain
import asyncio

# 3rd-party
import discord
import discord.ext.commands as commands

# 1st-party
from .protocol.lobby import LobbyPlayers
from .protocol.main_cog import add_game, GameView

class DummyGame(GameView):

    name: str = 'dummygame'
    wait_time: int = 20
    min_players: int = 2
    max_players: int = 3
    max_spectators: int = 0

    players: LobbyPlayers
    spectators: LobbyPlayers

    def __init__(self, *, players: LobbyPlayers, spectators: LobbyPlayers):
        super(GameView, self).__init__(timeout=None)
        self.players = players
        self.spectators = spectators
        asyncio.create_task(self.game_callback())

    async def game_callback(self) -> None:
        """Play the game"""
        players = '\n'.join(player.mention for player in self.players.keys())
        spectators = '\n'.join(spectator.mention for spectator in self.spectators.keys())
        await asyncio.gather(*(
            msg.edit(embed=discord.Embed(
                description=f'Players:\n{players}\n\nSpectators:\n{spectators}'))
            for msg in chain(self.players.values(), self.spectators.values())
        ))

def setup(bot: commands.Bot):
    add_game(DummyGame)
