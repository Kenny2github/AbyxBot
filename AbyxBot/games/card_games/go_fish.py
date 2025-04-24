# stdlib
from abc import ABCMeta, abstractmethod
import asyncio
from logging import getLogger
from operator import attrgetter
from collections import Counter, deque
from dataclasses import dataclass, field, InitVar
from enum import Enum, auto
from random import shuffle
from typing import Optional, Union

# 3rd-party
import discord

# 1st-party
from ...consts.chars import BLACK_NUMS, BOOK
from ...i18n import Msg, error_embed, mkembed, mkmsg
from ...lib.utils import BroadcastQueue
from ..protocol.engine import GameEngine
from ..protocol.lobby import GameProperties, LobbyPlayers
from ..protocol.cmd import add_game
from .card import NUMBER_EMOJIS, PlayingCard

logger = getLogger(__name__)

suit_key = attrgetter('suit')
number_key = attrgetter('number')

@dataclass(eq=False)
class Player:
    idx: int
    deck: InitVar[list[PlayingCard]]
    hand: list[PlayingCard] = field(init=False)
    last_fish: Optional[PlayingCard] = field(init=False, default=None)
    books: list[list[PlayingCard]] = field(init=False, default_factory=list)

    def __post_init__(self, deck: list[PlayingCard]) -> None:
        self.hand = [deck.pop() for _ in range(7)]
        self.hand.sort(key=number_key)

    def take(self, number: int) -> list[PlayingCard]:
        taken = [card for card in self.hand if card.number == number]
        self.hand = [card for card in self.hand if card.number != number]
        return taken

    def receive(self, cards: list[PlayingCard]) -> None:
        self.hand.extend(cards)
        self.hand.sort(key=number_key)

    @property
    def number(self) -> str:
        if self.idx > 10:
            return ''.join(BLACK_NUMS[int(digit)] for digit in str(self.idx))
        return BLACK_NUMS[self.idx]

class EventType(Enum):
    TOOK_CARDS = auto()
    WENT_FISHING = auto()
    FISHED_CARD = auto()
    NEW_BOOK = auto()

class _Event(metaclass=ABCMeta):
    @property
    @abstractmethod
    def msg(self) -> Msg:
        raise NotImplementedError

@dataclass
class TookCards(_Event):
    cards: list[PlayingCard]
    taker: Player
    victim: Player

    @property
    def msg(self) -> Msg:
        return Msg('go_fish/took-cards', card=self.cards[0].number_emoji,
                   taker=self.taker.number, victim=self.victim.number,
                   count=len(self.cards))

@dataclass
class WentFishing(_Event):
    number: int
    fisher: Player
    fish: Player

    @property
    def msg(self) -> Msg:
        return Msg('go_fish/went-fishing', number=NUMBER_EMOJIS[self.number],
                   fisher=self.fisher.number, fish=self.fish.number)

@dataclass
class FishedCard(_Event):
    card: PlayingCard
    fisher: Player
    fish: Player

    @property
    def msg(self) -> Msg:
        return Msg('go_fish/fished-card', number=self.card.number_emoji,
                   card=self.card.as_emoji, fisher=self.fisher.number,
                   fish=self.fish.number)

@dataclass
class NewBook(_Event):
    book: list[PlayingCard]
    author: Player

    @property
    def msg(self) -> Msg:
        return Msg('go_fish/new-book', author=self.author.number,
                   book=' '.join(card.as_emoji for card in self.book))

@dataclass
class HandEmptied(_Event):
    player: Player

    @property
    def msg(self) -> Msg:
        return Msg('go_fish/hand-emptied', player=self.player.number)

@dataclass
class Timeout(_Event):
    victim: Player

    @property
    def msg(self) -> Msg:
        return Msg('go_fish/timeout', victim=self.victim.number)

class GameStart(_Event):
    @property
    def msg(self) -> Msg:
        return Msg('go_fish/game-start')

Event = Union[TookCards, WentFishing, FishedCard,
              NewBook, HandEmptied, Timeout, GameStart]

class GoFishEngine(GameEngine):

    deck: list[PlayingCard]
    players: dict[discord.abc.User, Player]
    users: dict[Player, discord.abc.User]
    turns: deque[Player]
    events: deque[Event]

    @property
    def next_player(self) -> Player:
        return self.turns[0] # empty hand skipping is done by skip_unplayable()

    def __init__(self, players: LobbyPlayers) -> None:
        self.deck = PlayingCard.make_deck()
        shuffle(self.deck)
        self.players = {user: Player(i, self.deck) for i, user in enumerate(
            players.keys(), start=1)}
        self.users = {player: user for user, player in self.players.items()}
        self.turns = deque(self.users.keys())
        # maxlen set based on character limit for embed value (1024)
        # and length of longest event string (~200 at time of comment writing)
        self.events = deque(maxlen=5)
        self.events.append(GameStart())

    def advance_turn(self) -> None:
        self.turns.rotate()

    def skip_unplayable(self) -> None:
        if self.ended():
            return # otherwise infinite loop
        while not self.turns[0].hand:
            self.turns.rotate()

    def check_books(self) -> None:
        if not self.next_player.hand:
            return # no books makeable from empty
        counter = Counter(card.number for card in self.next_player.hand)
        for num, count in counter.items():
            if count < 4:
                continue # do not care
            book = self.next_player.take(num)
            book.sort(key=suit_key)
            self.next_player.books.append(book)
            self.events.append(NewBook(book, self.next_player))
        if not self.next_player.hand:
            # since this was checked against at the beginning, this means it is
            # newly emptied by book withdrawal
            self.events.append(HandEmptied(self.next_player))

    def timeout(self, victim: Player) -> None:
        del self.players[self.users.pop(victim)]
        self.turns.remove(victim)
        self.events.append(Timeout(victim))

    def update(self, victim: Player, number: int) -> None:
        taken = victim.take(number)
        if taken:
            self.next_player.receive(taken)
            self.next_player.last_fish = None
            self.check_books()
            self.events.append(TookCards(taken, self.next_player, victim))
        else:
            draw = self.deck.pop()
            self.next_player.hand.append(draw)
            self.next_player.hand.sort(key=number_key)
            self.next_player.last_fish = draw
            self.check_books()
            if draw.number == number:
                self.events.append(FishedCard(draw, self.next_player, victim))
            else:
                self.events.append(WentFishing(number, self.next_player, victim))
                # NOTE: must come after appending event
                self.advance_turn()
        self.skip_unplayable()

    def ended(self) -> bool:
        # a game of fish ends only when everyone has made all their books
        return not any(player.hand for player in self.turns)

    def book_counts(self) -> Counter[Player]:
        counts = Counter({player: 0 for player in self.players.values()})
        counts.update(player for player in self.turns for book in player.books)
        return counts

class GoFishView(discord.ui.View):

    viewer: discord.abc.User
    players: LobbyPlayers
    game: GoFishEngine
    notifications: BroadcastQueue[Optional['GoFishView']]
    notifications_task: asyncio.Task[None]

    @property
    def viewer_msg(self) -> discord.Message:
        return self.players[self.viewer]
    @viewer_msg.setter
    def viewer_msg(self, value: discord.Message) -> None:
        self.players[self.viewer] = value

    def __init__(self, *, viewer: discord.abc.User, game: GoFishEngine,
                 notifications: BroadcastQueue[Optional['GoFishView']],
                 players: LobbyPlayers) -> None:
        super().__init__(timeout=600) # 10 minutes
        self.viewer = viewer
        self.players = players
        self.game = game
        self.notifications = notifications
        self.notifications_task = asyncio.create_task(
            self.respond_to_notifications())
        # initialize components
        self.victim.placeholder = mkmsg(self.viewer, 'go_fish/select-victim')
        self.number.placeholder = mkmsg(self.viewer, 'go_fish/select-number')

    async def interaction_check(self, ctx: discord.Interaction) -> bool:
        if ctx.user != self.viewer:
            await ctx.response.send_message(embed=error_embed(
                ctx, Msg('connect4/not-yours')), ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        self.game.timeout(self.game.players[self.viewer])
        self.notifications.put_nowait(self)
        await self.viewer_msg.reply(embed=mkembed(
            self.viewer, title=Msg('go_fish/timed-out-title'),
            description=Msg('go_fish/timed-out', self.timeout),
            color=discord.Color.red()))
        await self.viewer_msg.edit(view=None)

    async def respond_to_notifications(self) -> None:
        with self.notifications.consume() as queue:
            while 1:
                sender = await queue.get()
                logger.debug('Game %x: view for %s was notified by view for %s',
                             id(self.game), self.viewer,
                             None if sender is None else sender.viewer)
                self.timeout = self.timeout # reset timeout
                if sender is not self:
                    await self.render_game()
                if len(self.game.players) < 2: # everyone else timed out
                    await self.viewer_msg.reply(embed=mkembed(
                        self.viewer, title=Msg('go_fish/all-timed-out-title'),
                        description=Msg('go_fish/all-timed-out', self.timeout),
                        color=discord.Color.red()))
                    await self.viewer_msg.edit(view=None)
                    self.stop()
                    return

    # methods for constructing the main embed

    def format_player_books(self, book_counts: dict[Player, int]) -> str:
        return '\n'.join(
            f'{player.number}: {self.game.users[player]!s}'
            f' ({self.game.users[player].id}) - {count} {BOOK}'
            for player, count in book_counts.items())

    def add_players_field(self, player: discord.abc.User,
                          embed: discord.Embed) -> None:
        players = self.format_player_books(self.game.book_counts())
        embed.add_field(
            name=mkmsg(player, 'go_fish/players-title'),
            value=players, inline=False)

    def add_hand_field(self, player: discord.abc.User,
                       embed: discord.Embed) -> None:
        game_player = self.game.players[player]

        hand = ' '.join(card.as_emoji for card in game_player.hand)
        if not hand:
            hand = mkmsg(player, 'go_fish/empty-hand')
        embed.add_field(
            name=mkmsg(player, 'go_fish/hand-title'),
            value=hand, inline=False)

    def add_books_field(self, player: discord.abc.User,
                        embed: discord.Embed) -> None:
        game_player = self.game.players[player]

        books = '\n'.join(' '.join(card.as_emoji for card in book)
                          for book in game_player.books)
        if not books:
            books = mkmsg(player, 'go_fish/no-books')
        embed.add_field(
            name=mkmsg(player, 'go_fish/books-title'),
            value=books, inline=False)

    def add_events_field(self, player: discord.abc.User,
                         embed: discord.Embed) -> None:
        events: list[str] = []
        for event in self.game.events:
            msg = event.msg
            msg.set_lang(player)
            events.append(str(msg))
        embed.add_field(
            name=mkmsg(player, 'go_fish/events-title'),
            value='\n'.join(events), inline=False)

    def add_fish_field(self, player: discord.abc.User,
                       embed: discord.Embed) -> None:
        last_fish = self.game.players[player].last_fish
        if last_fish:
            embed.add_field(
                name=mkmsg(player, 'go_fish/last-fish-title'),
                value=last_fish.as_emoji
            )

    def make_game_embed(self, player: discord.abc.User) -> discord.Embed:
        game_player = self.game.players[player]
        embed = mkembed(
            player, title=Msg('go_fish/view-title'),
            description=Msg('go_fish/view-description', game_player.number),
            footer=Msg('go_fish/next-turn', self.game.next_player.idx))
        self.add_players_field(player, embed)
        self.add_hand_field(player, embed)
        self.add_books_field(player, embed)
        self.add_events_field(player, embed)
        self.add_fish_field(player, embed)
        return embed

    # end methods for constructing the main embed

    async def render_game(self, ctx: Optional[discord.Interaction] = None
                          ) -> None:
        # update select choices
        self.victim.options = [
            discord.SelectOption(
                label=str(user),
                emoji=None if player.idx > 10 else player.number,
                value=str(user.id),
            )
            for user, player in sorted(
                self.game.players.items(),
                key=lambda i: i[1].idx
            )
            if user != self.viewer
        ]
        self.number.options = [
            discord.SelectOption(
                label=PlayingCard(number=number).number_ascii,
                emoji=PlayingCard(number=number).number_emoji,
                value=str(number),
            )
            for number in sorted(set(
                card.number for card in self.game.players[self.viewer].hand
            ))
        ]

        embed = self.make_game_embed(self.viewer)

        my_turn = self.game.next_player is self.game.players[self.viewer]
        ended = self.game.ended()
        show_view = bool(my_turn and not ended and self.game.next_player.hand)

        kwargs = {
            'content': None,
            'embed': embed,
            'view': self if show_view else None,
        }
        if ctx is None:
            self.viewer_msg = await self.viewer_msg.edit(**kwargs)
        else: # caused by interaction, not notification
            self.victim.disabled = self.number.disabled = False
            self.victim_selection = self.number_selection = None
            self.notifications.put_nowait(self)
            await ctx.response.edit_message(**kwargs)
            self.viewer_msg = await ctx.original_response()

        if ended:
            book_counts = self.game.book_counts()
            max_books: int = max(book_counts.values())
            winners = self.format_player_books({
                player: count for player, count in book_counts.items()
                if count == max_books})
            await self.viewer_msg.reply(embed=mkembed(
                ctx or self.viewer, title=Msg('go_fish/winners-title'),
                description=Msg('go_fish/winners', winners)
            ))
            self.stop()

    # actual components

    victim_selection: Optional[Player] = None
    number_selection: Optional[int] = None

    @discord.ui.select()
    async def victim(self, ctx: discord.Interaction,
                     select: discord.ui.Select) -> None:
        victim = ctx.client.get_user(int(select.values[0]))
        assert victim is not None
        self.victim_selection = self.game.players[victim]
        if self.number_selection is None:
            # first interaction of the pair
            self.victim.disabled = True
            await ctx.response.edit_message(
                embed=self.make_game_embed(self.viewer), view=self)
            self.viewer_msg = await ctx.original_response()
        else:
            # second interaction of the pair
            self.game.update(self.victim_selection, self.number_selection)
            await self.render_game(ctx)

    @discord.ui.select()
    async def number(self, ctx: discord.Interaction,
                     select: discord.ui.Select) -> None:
        number = int(select.values[0])
        self.number_selection = number
        if self.victim_selection is None:
            # first interaction
            self.number.disabled = True
            await ctx.response.edit_message(
                embed=self.make_game_embed(self.viewer), view=self)
            self.viewer_msg = await ctx.original_response()
        else:
            # second interaction
            self.game.update(self.victim_selection, self.number_selection)
            await self.render_game(ctx)

class GoFish(GameProperties, game_id=20):

    name: str = 'go_fish'
    wait_time: int = 30
    min_players: int = 2
    max_players: int = 2#None = None
    max_specators: int = 0
    # dm_only: bool = True

    def __init__(self, *, players: LobbyPlayers, spectators: LobbyPlayers) -> None:
        game = GoFishEngine(players)
        bq = BroadcastQueue()
        for viewer in players.keys():
            GoFishView(viewer=viewer, game=game,
                       notifications=bq, players=players)
        asyncio.create_task(bq.put(None))

def setup(bot: discord.Client):
    add_game(GoFish)
