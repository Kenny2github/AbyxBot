from __future__ import annotations

# stdlib
import asyncio
from typing import Any, Callable, Coroutine, Optional, TypeVar

# 3rd-party
import discord

# 1st-party
from ...i18n import Context, Msg

T = TypeVar('T')

def set_pop_n(s: set[T], n: int) -> set[T]:
    """Pop at most n items from the set s and return them as a new set."""
    result = set()
    for _ in range(n):
        try:
            result.add(s.pop())
        except KeyError:
            break
    return result

class LobbyMeta(type):
    """Classes with this as their metaclass are singletons."""
    _instances = {}

    def __call__(cls, *args, **kwargs) -> LobbyMeta:
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

class UserQueue:
    """Operations on multiple lobbies."""
    queue: dict[Optional[discord.User], set[Context]]
    backmap: dict[Context, Optional[discord.User]]

    def __init__(self) -> None:
        self.queue = {None: set()}
        self.backmap = {}

    def add(self, player: Context,
            queue_key: Optional[discord.User] = None) -> None:
        """Add a player to the queue and the backmap."""
        self.queue.setdefault(queue_key, set()).add(player)
        self.backmap[player] = queue_key

    def remove(self, player: Context) -> None:
        """Remove a player from the queue, whether they're in it or not."""
        self.queue.get(
            self.backmap.pop(player, None), set()
        ).discard(player)

    def queued(self, queue_key: Optional[discord.User] = None) -> set[Context]:
        """Get the players queued in the respective queue."""
        return self.queue.get(queue_key, set()).copy()

    def __contains__(self, player: Context) -> bool:
        """Check if a player is in queue."""
        return player in self.backmap

class Lobby(metaclass=LobbyMeta):
    """Base class for a queue.

    Each subclass of this class should represent a different game,
    by virtue of the fact that it will be a different queue.
    """

    # master queues
    player_queue: UserQueue
    spectator_queue: UserQueue
    # tasks that wait for players before starting
    timeout_tasks: dict[Optional[Context], asyncio.Task]
    # callback invoked with player and spectator sets
    game_callback: Callable[[set[Context], set[Context]],
                            Coroutine[Any, Any, None]]

    def __init__(self, coro) -> None:
        self.player_queue = UserQueue()
        self.spectator_queue = UserQueue()
        self.timeout_tasks = {}
        self.game_callback = coro

    # subclass properties

    @property
    def name(self) -> str:
        """i18n key for this game's name"""
        raise NotImplementedError

    @property
    def wait_time(self) -> int:
        """How many seconds to wait before automatically starting the game."""
        raise NotImplementedError

    @property
    def min_players(self) -> int:
        """Number of players needed to start the game at all."""
        return 2

    @property
    def max_players(self) -> Optional[int]:
        """Number of players needed to immediately start the game.
        None means unlimited players.

        When min_players <= len(queue) < max_players, the lobby will
        wait for wait_time before automatically starting the game.
        However, if len(queue) >= max_players, the lobby will immediately
        start the game with the max number of players popped from the queue.
        """
        return 2

    @property
    def max_spectators(self) -> Optional[int]:
        """Number of spectators allowed in a match (not including players).
        None means unlimited spectators.

        If >0, the lobby will continue waiting for wait_time before
        automatically starting the game even if max_players has been reached,
        to allow spectators some time to join.
        """
        return 0

    async def join(self, player: Context,
                   queue_key: Optional[discord.User] = None) -> None:
        """Join a player to the queue. Optionally, restrict their playmates."""
        self.player_queue.add(player, queue_key)
        await self.process_triggers(queue_key)
        await player.respond(embed=player.embed(
            Msg('lobby/joined-game-title'),
            Msg('lobby/joined-game', player.msg(self.name)),
            color=discord.Color.blue()
        ))

    async def spectate(self, spectator: Context,
                       queue_key: Optional[discord.User] = None) -> None:
        """Join a spectator to that queue. Optionally, restrict spectatees."""
        self.spectator_queue.add(spectator, queue_key)
        await self.process_triggers(queue_key)
        await spectator.respond(embed=spectator.embed(
            Msg('lobby/spectating-game-title'),
            Msg('lobby/spectating-game', spectator.msg(self.name)),
            color=discord.Color.blue()
        ))

    async def leave(self, player: Context) -> None:
        """Leave a player or a spectator from their queue."""
        if player in self.player_queue:
            queue_key = self.player_queue.backmap[player]
            self.player_queue.remove(player)
        elif player in self.spectator_queue:
            queue_key = self.spectator_queue.backmap[player]
            self.spectator_queue.remove(player)
        else:
            await player.respond(embed=player.error_embed(
                Msg('lobby/nothing-to-leave')))
            return
        await self.process_triggers(queue_key)
        await player.respond(embed=player.embed(
            Msg('lobby/left-title'),
            Msg('lobby/left', player.msg(self.name)),
            color=discord.Color.dark_gray()
        ))

    async def process_triggers(self, queue_key: Optional[discord.User]) -> None:
        """Handle trigger cases:
        - Max players reached; start immediately
        - Min players reached; start timing out
        - No longer min players reached; stop timing out
        """
        queued = self.player_queue.queued(queue_key)
        q_count = len(queued)
        # TODO: Wait for spectators if allowed
        if q_count >= self.max_players:
            # immediately start
            if queue_key in self.timeout_tasks:
                # already timing out and we're now beyond max - cancel timeout;
                # the cancellation handling will figure it out
                self.timeout_tasks[queue_key].cancel()
            else:
                await self.start(
                    queued, self.spectator_queue.queued(queue_key))
        elif q_count >= self.min_players:
            if queue_key not in self.timeout_tasks:
                # start the timeout
                self.timeout_tasks[queue_key] = asyncio.create_task(
                    self.timeout(queue_key))
        elif queue_key in self.timeout_tasks:
            # not enough players, but still timing out - cancel timeout;
            # the cancellation handling will take this into account
            self.timeout_tasks[queue_key].cancel()

    async def start(self, queued_players: set[Context],
              queued_spectators: set[Context]) -> None:
        """Start the game with the correct number of people."""
        players = set_pop_n(queued_players, self.max_players)
        spectators = set_pop_n(queued_spectators, self.max_spectators)
        for player in players:
            self.player_queue.remove(player)
        for spectator in spectators:
            self.spectator_queue.remove(spectator)
        await asyncio.gather(*(
            player.webhook.send(embed=player.embed(
                Msg('lobby/starting-now-title'),
                Msg('lobby/starting-now', player.msg(self.name)),
                color=discord.Color.blue()
            )) for player in players | spectators))
        asyncio.create_task(self.game_callback(players, spectators))

    async def timeout(self, queue_key: Optional[discord.User]) -> None:
        """Wait the allotted time, then start the game."""
        await asyncio.gather(*(
            player.webhook.send(embed=player.embed(
                Msg('lobby/starting-soon-title'),
                Msg('lobby/starting-soon',
                    player.msg(self.name), self.wait_time),
                color=discord.Color.blue()
            )) for player in self.player_queue.queued(queue_key)
            | self.spectator_queue.queued(queue_key)))
        try:
            await asyncio.sleep(self.wait_time)
        except asyncio.CancelledError:
            # either we are immediately starting or we're below minimum again
            # the code afterwards checks that, so we pass here
            pass
        # in any case, this task will be over soon, so unbind it
        del self.timeout_tasks[queue_key]
        queued = self.player_queue.queued(queue_key)
        spectating = self.spectator_queue.queued(queue_key)
        if len(queued) < self.min_players:
            # not enough players, don't start
            await asyncio.gather(*(
                player.webhook.send(embed=player.embed(
                    Msg('lobby/start-cancelled-title'),
                    Msg('lobby/start-cancelled', player.msg(self.name)),
                    color=discord.Color.blue()
                )) for player in queued | spectating))
            return
        # min players still fulfilled, start the game
        await self.start(queued, spectating)
