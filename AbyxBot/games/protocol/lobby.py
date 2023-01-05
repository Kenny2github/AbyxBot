# stdlib
from datetime import timedelta
from abc import ABCMeta, abstractmethod
from logging import getLogger
from collections import defaultdict
from enum import Enum, auto
from typing import Optional
from dataclasses import dataclass, field
import asyncio

# 3rd-party
import discord

# 1st-party
from ...i18n import Msg, error_embed, mkembed, mkmsg
from ...lib.database import id_to_game, game_to_id
from ...lib.utils import BroadcastQueue, dict_pop_n

logger = getLogger(__name__)

LobbyPlayers = dict[discord.abc.User, discord.Message]

class GameProperties(metaclass=ABCMeta):
    """Base class for an interactive experience."""

    @abstractmethod
    def __init__(self, *, players: LobbyPlayers, spectators: LobbyPlayers) -> None:
        """Initialize the game. This should involve a number of things:

        * Create a view instance for each player and spectator, and handle the
          passing of data between them. Note that this is a synchronous method
          so to call an async function, create a task for it.
        * Update the messages stored in the values of the players and
          spectators dicts. These were made for you by the lobby mechanics.
          Note that those messages have content, which you will need to clear.
        """
        raise NotImplementedError

    def __init_subclass__(cls, game_id: int) -> None:
        """Register this game with its enum ID."""
        id_to_game[game_id] = cls.name
        game_to_id[cls.name] = game_id

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

    @classmethod
    @property
    def dm_only(cls) -> bool:
        """Whether this game can only be played in DMs."""
        return False

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

    # host => updates
    updates: dict[Optional[discord.abc.User], BroadcastQueue[Update]] = field(
        default_factory=lambda: defaultdict(BroadcastQueue))

    def remove_private(self, host: discord.abc.User) -> None:
        for d in (
            self.players, self.spectators, self.updates
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
    game: type[GameProperties]

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
        def updates(self) -> BroadcastQueue[Update]:
            return self.lobby.updates[self.host]

    # overridden methods

    def __post_init__(self) -> None:
        super().__init__(timeout=None)
        asyncio.create_task(self.display_players())
        self.updater_task = asyncio.create_task(self.update_state())
        if self.game.max_spectators == 0:
            self.remove_item(self.spectate)
        if self.host is None:
            self.remove_item(self.start)
        self.join.label = mkmsg(self.viewer, 'lobby/join-button')
        self.leave.label = mkmsg(self.viewer, 'lobby/leave-button')
        self.spectate.label = mkmsg(self.viewer, 'lobby/spectate-button')
        self.start.label = mkmsg(self.viewer, 'lobby/start-button')

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
        with self.updates.consume() as queue:
            while 1:
                msg = await queue.get()
                try:
                    if msg == Update.PLAYERS:
                        await self.display_players()
                    elif msg == Update.STARTED and self.host is not None:
                        # disable further joins
                        self.message = await self.message.edit(view=None)
                        self.stop()
                        return
                    elif msg == Update.STARTED:
                        # update after removing from lobby
                        await self.display_players()
                finally:
                    queue.task_done()

    async def start_game(self) -> None:
        """Start the game."""
        logger.info('Starting game %r', self.name)
        # cancel the pending timeout, if any
        if self.timeout_task is not None:
            self.timeout_task.cancel()
            self.timeout_task = None
        if self.host is not None:
            # display final player/spectator list
            await self.update_brethren(Update.PLAYERS)
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
        logger.info('Scheduling %s-second wait before starting %r',
                    self.game.wait_time, self.name)
        loop = asyncio.get_running_loop()
        self.timeout_task = loop.call_later(
            self.game.wait_time, lambda: loop.create_task(self.start_game()))

    async def update_brethren(self, msg: Update) -> None:
        """Notify other views that the lobby state has changed."""
        self.updates.put_nowait(msg)
        await self.updates.join()

    async def make_message(self, ctx: discord.Interaction,
                           players: LobbyPlayers) -> None:
        thread_name = f"{mkmsg(ctx, 'games/' + self.name)} - {ctx.user.id}"
        resp = None
        thread = None
        if isinstance(ctx.channel, discord.TextChannel):
            thread = discord.utils.find(lambda t: t.name == thread_name,
                                        ctx.channel.threads)
        if thread is None:
            try:
                await ctx.response.send_message(content=mkmsg(
                    ctx, 'lobby/thread-placeholder', ctx.user.mention))
                resp = await (await ctx.original_response()).fetch()
                thread = await resp.create_thread(name=thread_name)
            except (discord.Forbidden, discord.HTTPException):
                # can't create threads
                pass
        # placeholder message that will become the game UI later
        if thread is not None: # successfully created/found thread
            msg = await thread.send(content=mkmsg(
                ctx, 'lobby/thread-msg-placeholder', ctx.user.mention))
            if resp is None: # found, not created
                await ctx.response.send_message(
                    content=msg.jump_url, ephemeral=True)
        elif resp is not None: # responded, couldn't make thread
            msg = await resp.edit(content=mkmsg(
                ctx, 'lobby/placeholder', ctx.user.mention))
        else: # didn't respond, couldn't make thread
            await ctx.response.send_message(content=mkmsg(
                ctx, 'lobby/placeholder', ctx.user.mention))
            msg = await (await ctx.original_response()).fetch()
        # map player user to game message
        players[ctx.user] = msg

    async def unmake_message(self, ctx: discord.Interaction,
                             players: LobbyPlayers) -> None:
        msg = players[ctx.user]
        if isinstance(msg.channel, discord.Thread):
            thread = msg.channel
            starter = thread.starter_message
            if starter is None:
                try:
                    starter = await thread.fetch_message(thread.id)
                except discord.NotFound:
                    _parent = thread.parent
                    if isinstance(_parent, discord.TextChannel):
                        try:
                            starter = await _parent.fetch_message(thread.id)
                        except discord.NotFound:
                            pass
            try:
                await thread.delete()
            except discord.Forbidden:
                pass
            if starter is not None:
                try:
                    await starter.delete()
                except discord.Forbidden:
                    pass
        try:
            await msg.delete()
        except discord.Forbidden:
            pass
        del players[ctx.user]

    # actual buttons

    @discord.ui.button(style=discord.ButtonStyle.primary)
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
        logger.info('User %s\t(%s) joining game %r',
                    ctx.user, ctx.user.id, self.name)
        await self.make_message(ctx, self.players)
        # update state
        if len(self.players) == self.game.max_players:
            # just reached max from below

            # if no spectators are allowed, start immediately
            if self.game.max_spectators == 0:
                await self.start_game()
            # if we're full on spectators AND players, start immediately
            elif self.game.max_spectators is None:
                pass # always wait for timeout or host start
            elif len(self.spectators) >= self.game.max_spectators:
                await self.start_game()
            # otherwise, let timeout continue
        # not an elif because both may need to happen at once
        if len(self.players) == self.game.min_players:
            # just reached min from below
            if self.host is None:
                # only timeout if no host
                await self.schedule_start()
        await self.update_brethren(Update.PLAYERS)

    @discord.ui.button(style=discord.ButtonStyle.danger)
    async def leave(self, ctx: discord.Interaction,
                    button: discord.ui.Button) -> None:
        if ctx.user in self.players:
            logger.info('User %s\t(%s) leaving game %r',
                        ctx.user, ctx.user.id, self.name)
            # remove from players
            await self.unmake_message(ctx, self.players)
        elif ctx.user in self.spectators:
            logger.info('User %s\t(%s) de-spectating game %r',
                        ctx.user, ctx.user.id, self.name)
            # remove from spectators
            await self.unmake_message(ctx, self.spectators)
        else:
            logger.info('User %s\t(%s) not in game %r',
                        ctx.user, ctx.user.id, self.name)
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

    @discord.ui.button(style=discord.ButtonStyle.secondary)
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
        logger.info('User %s\t(%s) spectating game %r',
                    ctx.user, ctx.user.id, self.name)
        await self.make_message(ctx, self.spectators)
        # update state
        # Unlike join(), we check for spectators here
        # and don't check the min_players at all.
        # Instead, we only do anything if we just reach max spectators,
        # and even then only if we're full on players too.
        if len(self.spectators) == self.game.max_spectators:
            # just reached max from below
            if self.game.max_players is None:
                pass # always wait for timeout or host instruction
            elif len(self.players) >= self.game.max_players:
                await self.start_game()
        await self.update_brethren(Update.PLAYERS)

    @discord.ui.button(style=discord.ButtonStyle.success)
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
        logger.info('User %s\t(%s) starting game %r',
                    ctx.user, ctx.user.id, self.name)
        await ctx.response.send_message(embed=mkembed(
            ctx, description=Msg('lobby/starting'),
            color=discord.Color.green()
        ), ephemeral=True)
        await self.start_game()
