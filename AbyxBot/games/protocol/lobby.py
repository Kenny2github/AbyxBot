# stdlib
from datetime import timedelta
from abc import ABCMeta, abstractmethod
from collections import defaultdict
from enum import Enum, auto
from typing import Optional
from dataclasses import dataclass, field
import asyncio

# 3rd-party
import discord

# 1st-party
from ...i18n import Msg, error_embed, mkembed, mkmsg
from ...utils import dict_pop_n

LobbyPlayers = dict[discord.abc.User, discord.Message]

class GameView(discord.ui.View, metaclass=ABCMeta):
    """Base class for an interactive experience."""

    @abstractmethod
    def __init__(self, *, players: LobbyPlayers, spectators: LobbyPlayers) -> None:
        """Initialize the view. This should involve a number of things:

        * Call ``super(GameView, self).__init__(timeout=<timeout>)``.
          By default, ``discord.ui.View``'s timeout is 180 seconds, which is
          probably not what you want. Therefore you need to call the super
          constructor of *this* class, not your own.
        * Update the messages stored in the values of the players and
          spectators dicts. These were made for you by the lobby mechanics.
        """
        raise NotImplementedError

    @classmethod
    @property
    @abstractmethod
    def name(cls) -> str:
        """The name of the game."""
        raise NotImplementedError

    @classmethod
    @property
    @abstractmethod
    def wait_time(cls) -> int:
        """How long to wait before starting (public lobbies only)."""
        raise NotImplementedError

    @classmethod
    @property
    def min_players(cls) -> int:
        """The minimum number of players required to start."""
        return 2

    @classmethod
    @property
    def max_players(cls) -> Optional[int]:
        """The maximum number of players allowed in a game.
        None for no maximum.
        """
        return 2

    @classmethod
    @property
    def max_spectators(cls) -> Optional[int]:
        """The maximum number of spectators allowed in a game.
        None for no maximum.
        """
        return 0

class Update(Enum):
    """The type of update being broadcast."""
    PLAYERS = auto()
    STARTED = auto()

@dataclass
class Lobby:
    """Container for game-wide lobby data."""
    # host => player => message
    players: dict[Optional[discord.abc.User], LobbyPlayers] = field(
        default_factory=lambda: defaultdict(dict))
    spectators: dict[Optional[discord.abc.User], LobbyPlayers] = field(
        default_factory=lambda: defaultdict(dict))

    timeout_task: Optional[asyncio.TimerHandle] = field(
        init=False, default=None)

    # host => event
    update_events: dict[Optional[discord.abc.User], asyncio.Event] = field(
        default_factory=lambda: defaultdict(asyncio.Event))
    # host => update
    update_values: dict[Optional[discord.abc.User], Optional[Update]] = field(
        default_factory=lambda: defaultdict(lambda: None))

    def remove_private(self, host: discord.abc.User) -> None:
        for d in (
            self.players, self.spectators,
            self.update_events, self.update_values
        ):
            del d[host]

lobbies: dict[str, Lobby] = defaultdict(Lobby)

@dataclass
class LobbyView(discord.ui.View):
    """A view for a game's lobby."""

    # passed by /game
    message: discord.Message # the message this view is attached to
    viewer: discord.abc.User # the user who requested the view, for i18n

    # properties of game
    game: type[GameView]

    # passed by /game
    host: Optional[discord.abc.User] = None

    # instance attribute
    updater_task: asyncio.Task[None] = field(init=False, repr=False)

    if 1: # shortcut properties
        # wrapped in if 1: block for easier collapsing

        @property
        def name(self) -> str:
            """Shortcut to the property of the game view class."""
            return self.game.name

        @property
        def lobby(self) -> Lobby:
            """The lobby for this game specifically."""
            return lobbies[self.name]

        @property
        def players(self) -> LobbyPlayers:
            """The players queued for this game specifically."""
            return self.lobby.players[self.host]

        @property
        def spectators(self) -> LobbyPlayers:
            """The spectators queued for this game specifically."""
            return self.lobby.spectators[self.host]

        @property
        def timeout_task(self) -> Optional[asyncio.TimerHandle]:
            """Shortcut to the corresponding Lobby attribute."""
            return self.lobby.timeout_task
        @timeout_task.setter
        def timeout_task(self, task: Optional[asyncio.TimerHandle]) -> None:
            self.lobby.timeout_task = task

        @property
        def update_event(self) -> asyncio.Event:
            return self.lobby.update_events[self.host]

        @property
        def update_value(self) -> Optional[Update]:
            return self.lobby.update_values[self.host]
        @update_value.setter
        def update_value(self, value: Update) -> None:
            self.lobby.update_values[self.host] = value

    # overridden methods

    def __post_init__(self) -> None:
        super().__init__(timeout=None)
        asyncio.create_task(self.display_players())
        self.updater_task = asyncio.create_task(self.update_state())
        if self.host is None:
            self.remove_item(self.start)

    def __del__(self) -> None:
        self.updater_task.cancel()

    def stop(self) -> None:
        self.updater_task.cancel()
        return super().stop()

    # helper functions

    async def display_players(self) -> None:
        """Update the lobby display with the list of players and spectators."""
        # display pings *only* so that names inappropriate for the server
        # are only displayed to those who can see them through a server
        # in which they are appropriate
        players = '\n'.join(player.mention for player in self.players.keys())
        fields = [(Msg('lobby/players-title'),
                   players or Msg('none-paren'), True)]
        # if spectators are allowed, display them
        if self.game.max_spectators != 0:
            spectators = '\n'.join(
                spectator.mention for spectator in self.spectators.keys())
            fields.append((Msg('lobby/spectators-title'),
                           spectators or Msg('none-paren'), True))
        if self.host is not None:
            fields.append((Msg('lobby/host-title'), self.host.mention, True))
        if self.timeout_task is not None:
            when = discord.utils.utcnow() + timedelta(
                seconds=self.timeout_task.when()
                - asyncio.get_running_loop().time())
            when = discord.utils.format_dt(when, style='T')
            description = Msg('lobby/timing-out', when)
        elif self.host is not None and len(self.players) >= self.game.min_players:
            description = Msg('lobby/can-start', self.host.mention)
        else:
            description = None
        embed = mkembed(
            self.viewer,
            description=description,
            title=Msg('lobby/queued-title',
                      mkmsg(self.viewer, 'games/' + self.name)),
            fields=fields,
            color=discord.Color.blue(),
        )
        self.message = await self.message.edit(embed=embed, view=self)

    async def update_state(self) -> None:
        """Continuously poll for updates."""
        while 1:
            await self.update_event.wait()
            msg = self.update_value
            if msg == Update.PLAYERS:
                await self.display_players()
            elif msg == Update.STARTED and self.host is not None:
                # disable further joins
                self.message = await self.message.edit(view=None)
                self.stop()
                return
            elif msg == Update.STARTED:
                await self.display_players() # update after removing from lobby

    async def start_game(self) -> None:
        """Start the game."""
        # cancel the pending timeout, if any
        if self.timeout_task is not None:
            self.timeout_task.cancel()
            self.timeout_task = None
        # remove at most max players from the lobby
        if self.game.max_players is None:
            players = self.players.copy()
            self.players.clear()
        else:
            players = dict_pop_n(self.game.max_players, self.players)
        # remove at most max spectators from the lobby
        if self.game.max_spectators is None:
            spectators = self.spectators.copy()
            self.spectators.clear()
        else:
            spectators = dict_pop_n(self.game.max_spectators, self.spectators)
        # notify other views
        await self.update_brethren(Update.STARTED)
        # delete the private lobby
        if self.host is not None:
            self.lobby.remove_private(self.host)
        # create the game view and give it the popped players and spectators
        self.game(players=players, spectators=spectators)

    async def schedule_start(self) -> None:
        """Schedule the game to start after a timeout."""
        if self.timeout_task is not None:
            return # already scheduled
        loop = asyncio.get_running_loop()
        self.timeout_task = loop.call_later(
            self.game.wait_time, lambda: loop.create_task(self.start_game()))

    async def update_brethren(self, msg: Update) -> None:
        """Notify other views that the lobby state has changed."""
        self.update_value = msg
        self.update_event.set()
        # give a chance for other waiters to proceed
        await asyncio.sleep(0)
        self.update_event.clear()

    # actual buttons

    @discord.ui.button(label='Join', style=discord.ButtonStyle.primary)
    async def join(self, ctx: discord.Interaction,
                   button: discord.ui.Button) -> None:
        if (
            self.host is not None
            and self.game.max_players is not None
            and len(self.players) >= self.game.max_players
        ):
            await ctx.response.send_message(embed=error_embed(
                ctx, Msg('lobby/full')), ephemeral=True)
            return
        if ctx.user in self.players:
            await ctx.response.send_message(embed=error_embed(
                ctx, Msg('lobby/already-joined')), ephemeral=True)
            return
        # placeholder message that will become the game UI later
        await ctx.response.send_message(embed=mkembed(
            ctx, description=Msg('lobby/placeholder', ctx.user.mention)))
        # map player user to game message
        self.players[ctx.user] = await (await ctx.original_response()).fetch()
        # update state
        if len(self.players) == self.game.max_players:
            # just reached max from below

            # if no spectators are allowed, start immediately
            if self.game.max_spectators == 0:
                await self.start_game()
            # if we're full on spectators AND players, start immediately
            elif len(self.spectators) >= (self.game.max_spectators or 0):
                await self.start_game()
            # otherwise, let timeout continue
        # not an elif because both may need to happen at once
        if len(self.players) == self.game.min_players:
            # just reached min from below
            if self.host is None:
                # only timeout if no host
                await self.schedule_start()
        await self.update_brethren(Update.PLAYERS)

    @discord.ui.button(label='Leave', style=discord.ButtonStyle.danger)
    async def leave(self, ctx: discord.Interaction,
                    button: discord.ui.Button) -> None:
        if ctx.user in self.players:
            # remove from players
            await self.players[ctx.user].delete()
            del self.players[ctx.user]
        elif ctx.user in self.spectators:
            # remove from spectators
            await self.spectators[ctx.user].delete()
            del self.spectators[ctx.user]
        else:
            # not in lobby
            await ctx.response.send_message(ephemeral=True, embed=error_embed(
                ctx, Msg('lobby/nothing-to-leave')))
            return
        # cancel timeout if fallen below min players threshold
        if len(self.players) < self.game.min_players and self.timeout_task is not None:
            self.timeout_task.cancel()
            self.timeout_task = None
        await ctx.response.send_message(embed=mkembed(
            ctx, Msg('lobby/left-title'),
            Msg('lobby/left', mkmsg(ctx, 'games/' + self.name)),
            color=discord.Color.dark_red()
        ), ephemeral=True)
        await self.update_brethren(Update.PLAYERS)

    @discord.ui.button(label='Spectate', style=discord.ButtonStyle.secondary)
    async def spectate(self, ctx: discord.Interaction,
                       button: discord.ui.Button) -> None:
        if (
            self.host is not None
            and self.game.max_spectators is not None
            and len(self.spectators) >= self.game.max_spectators
        ) or self.game.max_spectators == 0:
            await ctx.response.send_message(embed=error_embed(
                ctx, Msg('lobby/full')), ephemeral=True)
            return
        if ctx.user in self.spectators:
            await ctx.response.send_message(embed=error_embed(
                ctx, Msg('lobby/already-joined')), ephemeral=True)
            return
        # placeholder message that will become the game UI later
        await ctx.response.send_message(embed=mkembed(
            ctx, description=Msg('lobby/placeholder', ctx.user.mention)))
        # map spectator user to game message
        self.spectators[ctx.user] = await (await ctx.original_response()).fetch()
        # update state
        # Unlike join(), we check for spectators here
        # and don't check the min_players at all.
        # Instead, we only do anything if we just reach max spectators,
        # and even then only if we're full on players too.
        if len(self.spectators) == self.game.max_spectators:
            # just reached max from below
            if len(self.players) >= (self.game.max_players or 0):
                await self.start_game()
        await self.update_brethren(Update.PLAYERS)

    @discord.ui.button(label='Start', style=discord.ButtonStyle.success)
    async def start(self, ctx: discord.Interaction,
                    button: discord.ui.Button) -> None:
        if ctx.user != self.host:
            await ctx.response.send_message(embed=error_embed(
                ctx, Msg('lobby/not-host')), ephemeral=True)
            return
        if len(self.players) < self.game.min_players:
            await ctx.response.send_message(embed=error_embed(
                ctx, Msg('lobby/too-few-players', self.game.min_players)
            ), ephemeral=True)
            return
        await ctx.response.send_message(embed=mkembed(
            ctx, description=Msg('lobby/starting'),
            color=discord.Color.green()
        ), ephemeral=True)
        await self.start_game()
