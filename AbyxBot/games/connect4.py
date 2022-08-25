# stdlib
from itertools import chain
from logging import getLogger
from typing import Optional
import asyncio

# # 3rd-party
from enum import Enum, auto
import discord

# 1st-party
from ..chars import BLUE_CIRCLE, NUMS, RED_CIRCLE, BLACK_SQUARE
from ..i18n import Msg, error_embed, mkembed, mkmsg
from ..utils import BroadcastQueue
from .protocol.engine import GameEngine
from .protocol.lobby import GameProperties, LobbyPlayers
from .protocol.main_cog import add_game

logger = getLogger(__name__)

NUMS = NUMS[1:8] # column numbers
DIM = 7 # dimension of board

class Player(Enum):
    NONE = BLACK_SQUARE
    RED = RED_CIRCLE
    BLUE = BLUE_CIRCLE

class Event(Enum):
    MOVE_MADE = auto()
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
        self.next_turn = self.after(self.next_turn)

    def won(self, player: Player, check_other: bool = True) -> Optional[bool]:
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

class Connect4View(discord.ui.View):

    viewer: discord.abc.User
    game: Connect4Engine
    events: BroadcastQueue[Event]

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
            Player.RED: discord.Color.red(),
            Player.BLUE: discord.Color.blue(),
        }[color]

    def __init__(self, *, viewer: discord.abc.User, game: Connect4Engine,
                 events: BroadcastQueue[Event],
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
        self.events.put_nowait(Event.TIMEOUT) # including ourselves

    async def consume_events(self) -> None:
        with self.events.consume() as queue:
            while 1:
                event = await queue.get()
                if event == Event.TIMEOUT:
                    logger.info('Game %x timed out', id(self.game))
                    await self.viewer_msg.edit(embed=mkembed(
                        self.viewer,
                        description=self.constructboard(),
                        footer=Msg('connect4/game-timeout', self.timeout),
                    ), view=None)
                    self.stop()
                    return
                elif event == Event.MOVE_MADE:
                    logger.debug('Game view %x updating from move', id(self))
                    await self.display_board()

    async def display_board(self, ctx: Optional[discord.Interaction] = None
                            ) -> None:
        self.play.disabled = self.game.next_turn != self.viewer_color

        kwargs = {
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

    def constructboard(self) -> str:
        lines: list[str] = []
        lines.append(mkmsg(self.viewer, 'connect4/player-color',
                           RED_CIRCLE, self.red_player.mention))
        lines.append(mkmsg(self.viewer, 'connect4/player-color',
                           BLUE_CIRCLE, self.blue_player.mention))
        lines.append(''.join(NUMS))
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

    @discord.ui.select(options=[
        discord.SelectOption(label=str(i + 1), emoji=NUMS[i])
        for i in range(7)
    ])
    async def play(self, ctx: discord.Interaction,
                   select: discord.ui.Select) -> None:
        self.game.update(int(select.values[0]) - 1)
        self.events.put_nowait(Event.MOVE_MADE)
        await self.display_board(ctx)

class Connect4(GameProperties):

    name: str = 'connect4'
    wait_time: int = 0
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
