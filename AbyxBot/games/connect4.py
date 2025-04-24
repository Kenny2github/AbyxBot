from __future__ import annotations
# stdlib
from itertools import chain
from logging import getLogger
from typing import Optional
import asyncio

# # 3rd-party
from enum import Enum, auto
import discord

# 1st-party
from ..consts.chars import BLUE_CIRCLE, BLACK_NUMS, RED_CIRCLE, BLACK_SQUARE, RED_X
from ..i18n import Msg, error_embed, mkembed, mkmsg
from ..lib.utils import BroadcastQueue
from .protocol.engine import GameEngine
from .protocol.lobby import GameProperties, LobbyPlayers
from .protocol.cmd import add_game

logger = getLogger(__name__)

NUMS = BLACK_NUMS[1:8] # column numbers
DIM = 7 # dimension of board

class Player(Enum):
    NONE = BLACK_SQUARE
    RED = RED_CIRCLE
    BLUE = BLUE_CIRCLE

class Event(Enum):
    MOVE_MADE = auto()
    GAME_OVER = auto()
    TIMEOUT = auto()

class Connect4Engine(GameEngine):

    board: list[list[Player]]
    next_turn: Player

    @staticmethod
    def after(turn: Player) -> Player:
        if turn == Player.BLUE:
            return Player.RED
        if turn == Player.RED:
            return Player.BLUE
        return Player.NONE

    def __init__(self) -> None:
        self.board = [[Player.NONE for _ in range(DIM)] for _ in range(DIM)]
        self.next_turn = Player.BLUE

    def update(self, column: int):
        for row in range(DIM):
            if self.board[row][column] != Player.NONE:
                self.board[row - 1][column] = self.next_turn
                break
        else:
            self.board[-1][column] = self.next_turn
        self.next_turn = self.after(self.next_turn)

    def ended(self) -> bool:
        return self.won(Player.BLUE) is not False

    def won(self, player: Player, check_other: bool = True) -> Optional[bool]:
        """Has the game ended by winning?

        Returns:
        * ``True`` for yes
        * ``None`` if the game has ended, but not by winning
        * ``False`` if the game has not yet ended
        """
        if player == Player.NONE:
            return False
        winning_run = [player] * 4
        # check -
        for row in range(DIM):
            for col in range(DIM - 3):
                run = [self.board[row][col + i] for i in range(4)]
                if run == winning_run:
                    return True
        # check |
        for row in range(DIM - 3):
            for col in range(DIM):
                run = [self.board[row + i][col] for i in range(4)]
                if run == winning_run:
                    return True
        # check \
        for row in range(3, DIM):
            for col in range(DIM - 3):
                run = [self.board[row - i][col + i] for i in range(4)]
                if run == winning_run:
                    return True
        # check /
        for row in range(DIM - 3):
            for col in range(DIM - 3):
                run = [self.board[row + i][col + i] for i in range(4)]
                if run == winning_run:
                    return True
        if check_other:
            if self.won(self.after(player), check_other=False):
                return None # ended, but not by winning
        for row in self.board:
            for tile in row:
                if tile == Player.NONE:
                    return False # not yet ended, free space left
        return None # ended, everyone lost

    def legal_columns(self) -> list[int]:
        return [col for col in range(DIM)
                if self.board[0][col] == Player.NONE]

class Connect4View(discord.ui.View):

    viewer: discord.abc.User
    game: Connect4Engine
    events: BroadcastQueue[EventWithSender]

    red_player: discord.abc.User
    red_message: discord.Message
    blue_player: discord.abc.User
    blue_message: discord.Message
    players: LobbyPlayers
    spectators: LobbyPlayers

    @property
    def viewer_msg(self) -> discord.Message:
        if self.viewer == self.red_player:
            return self.red_message
        if self.viewer == self.blue_player:
            return self.blue_message
        return self.spectators[self.viewer]
    @viewer_msg.setter
    def viewer_msg(self, value: discord.Message) -> None:
        if self.viewer == self.red_player:
            self.red_message = value
        elif self.viewer == self.blue_player:
            self.blue_message = value
        else:
            self.spectators[self.viewer] = value

    @property
    def viewer_color(self) -> Player:
        return {
            self.red_player: Player.RED,
            self.blue_player: Player.BLUE,
        }.get(self.viewer, Player.NONE)
    @property
    def viewer_discord_color(self) -> discord.Color:
        color = self.viewer_color
        if color == Player.NONE:
            color = self.game.next_turn
        return {
            # taken from red and blue circle emojis
            Player.RED: discord.Color.from_str('#DD2E44'),
            Player.BLUE: discord.Color.from_str('#55ACEE'),
        }[color]

    def __init__(self, *, viewer: discord.abc.User, game: Connect4Engine,
                 events: BroadcastQueue[EventWithSender],
                 players: LobbyPlayers, spectators: LobbyPlayers) -> None:
        super().__init__(timeout=600) # 10 minutes
        # set instance variables
        self.viewer = viewer
        self.game = game
        (self.red_player, self.red_message), \
            (self.blue_player, self.blue_message) = players.items()
        self.players = players
        self.spectators = spectators
        # initialize components
        if self.viewer in self.players:
            self.play.placeholder = mkmsg(self.viewer, 'connect4/select-column')
        else:
            self.remove_item(self.play)
        # display the board and view
        asyncio.create_task(self.display_board())
        # set up a consumer for events
        self.events = events
        self.events_task = asyncio.create_task(self.consume_events())

    async def interaction_check(self, ctx: discord.Interaction) -> bool:
        if ctx.user != self.viewer:
            await ctx.response.send_message(embed=error_embed(
                ctx, Msg('connect4/not-yours')), ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        self.events.put_nowait((self, Event.TIMEOUT))

    async def consume_events(self) -> None:
        with self.events.consume() as queue:
            while 1:
                sender, event = await queue.get()
                self.timeout = self.timeout # reset timeout
                logger.debug(
                    'Game %x: view for %s received %s from game view for %s',
                    id(self.game), self.viewer, event.name, sender.viewer)
                if event == Event.TIMEOUT:
                    logger.info('Game %x timed out', id(self.game))
                    await self.viewer_msg.edit(embed=mkembed(
                        self.viewer,
                        description=self.constructboard(),
                        footer=Msg('connect4/game-timeout', self.timeout),
                    ), view=None)
                    self.stop()
                    return
                elif event == Event.MOVE_MADE and sender is not self:
                    await self.display_board()
                elif event == Event.GAME_OVER and sender is not self:
                    await self.finalize()
                    self.stop()
                    return
                elif event == Event.GAME_OVER: # and sender is self
                    self.stop()
                    return

    async def display_board(self, ctx: Optional[discord.Interaction] = None
                            ) -> None:
        self.play.options = [
            discord.SelectOption(label=str(i + 1), emoji=NUMS[i])
            for i in self.game.legal_columns()
        ]
        self.play.disabled = self.game.next_turn != self.viewer_color

        kwargs = {
            'content': None,
            'embed': discord.Embed(
                description=self.constructboard(),
                color=self.viewer_discord_color),
            'view': self,
        }
        if ctx is None:
            self.viewer_msg = await self.viewer_msg.edit(**kwargs)
        else:
            await ctx.response.edit_message(**kwargs)
            self.viewer_msg = await ctx.original_response()

    async def finalize(self, ctx: Optional[discord.Interaction] = None,
                       ) -> None:
        if self.viewer in self.players:
            if self.game.won(self.viewer_color, check_other=False):
                key = 'connect4/you-win'
                winner = self.viewer
            elif self.game.won(self.game.after(self.viewer_color),
                            check_other=False):
                key = 'connect4/they-win'
                if self.viewer == self.blue_player:
                    winner = self.red_player
                else:
                    winner = self.blue_player
            else:
                key = 'connect4/nobody-wins'
                winner = None
        else:
            if self.game.won(Player.BLUE, check_other=False):
                key = 'connect4/someone-wins'
                winner = self.blue_player
            elif self.game.won(Player.RED, check_other=False):
                key = 'connect4/someone-wins'
                winner = self.red_player
            else:
                key = 'connect4/nobody-wins'
                winner = None

        lines = self.constructboard().splitlines()
        # replace your/their-turn line with winner line
        lines[-1] = mkmsg(ctx or self.viewer, key, winner)

        kwargs = {
            'embed': discord.Embed(
                description='\n'.join(lines),
                color=discord.Color.green()),
            'view': None,
        }
        if ctx is None:
            self.viewer_msg = await self.viewer_msg.edit(**kwargs)
        else:
            await ctx.response.edit_message(**kwargs)
            self.viewer_msg = await ctx.original_response()

    def constructboard(self) -> str:
        lines: list[str] = []
        lines.append(mkmsg(self.viewer, 'connect4/player-color',
                           RED_CIRCLE, self.red_player.mention))
        lines.append(mkmsg(self.viewer, 'connect4/player-color',
                           BLUE_CIRCLE, self.blue_player.mention))
        legal = self.game.legal_columns()
        lines.append(''.join(num if i in legal else RED_X
                             for i, num in enumerate(NUMS)))
        lines.extend(''.join(cell.value for cell in row)
                     for row in self.game.board)
        lines.append(mkmsg(self.viewer, 'connect4/you-are', self.viewer.mention))
        if self.viewer_color == Player.NONE:
            lines.append(mkmsg(self.viewer, 'connect4/turn-spectator',
                               self.game.next_turn.value))
        elif self.viewer_color == self.game.next_turn:
            lines.append(mkmsg(self.viewer, 'connect4/your-turn'))
        else:
            lines.append(mkmsg(self.viewer, 'connect4/their-turn'))
        return '\n'.join(lines)

    @discord.ui.select()
    async def play(self, ctx: discord.Interaction,
                   select: discord.ui.Select) -> None:
        self.game.update(int(select.values[0]) - 1)
        if self.game.won(Player.BLUE) is False:
            self.events.put_nowait((self, Event.MOVE_MADE))
            # False = game not ended, regardless of who's being checked
            await self.display_board(ctx)
        else:
            self.events.put_nowait((self, Event.GAME_OVER))
            await self.finalize(ctx)

EventWithSender = tuple[Connect4View, Event]

class Connect4(GameProperties, game_id=10):

    name: str = 'connect4'
    wait_time: int = 30
    min_players: int = 2
    max_players: int = 2
    max_spectators: None = None

    def __init__(self, *, players: LobbyPlayers, spectators: LobbyPlayers) -> None:
        game = Connect4Engine()
        bq = BroadcastQueue()
        for viewer in chain(players.keys(), spectators.keys()):
            Connect4View(viewer=viewer, game=game, events=bq,
                         players=players, spectators=spectators)

def setup(bot: discord.Client):
    add_game(Connect4)
