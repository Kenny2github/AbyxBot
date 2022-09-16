from __future__ import annotations

# stdlib
from dataclasses import dataclass
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing_extensions import Self

# 3rd-party

# 1st-party
from ...chars import (
    DIAMONDS, CLUBS, HEARTS, SPADES,
    REGI, NUMS
)

SUIT_EMOJIS = (DIAMONDS, CLUBS, HEARTS, SPADES)
#                  A                   J        Q         K
NUMBER_EMOJIS = (REGI[0], *NUMS[2:], REGI[9], REGI[16], REGI[10])

SUIT_STRS = ('D', 'C', 'H', 'S')
NUMBER_STRS = tuple('A 2 3 4 5 6 7 8 9 10 J Q K'.split())

@dataclass
class PlayingCard:

    suit: int = 0
    number: int = 0

    @property
    def suit_ascii(self) -> str:
        return SUIT_STRS[self.suit]
    @property
    def number_ascii(self) -> str:
        return NUMBER_STRS[self.number]
    @property
    def as_ascii(self) -> str:
        return self.number_ascii + self.suit_ascii

    @property
    def suit_emoji(self) -> str:
        return SUIT_EMOJIS[self.suit]
    @property
    def number_emoji(self) -> str:
        return NUMBER_EMOJIS[self.number]
    @property
    def as_emoji(self) -> str:
        return f'{self.number_emoji}\N{WORD JOINER}{self.suit_emoji}'

    @classmethod
    def make_deck(cls) -> list[Self]:
        return [cls(suit, num) for suit in range(4) for num in range(13)]

    def __hash__(self) -> int:
        return hash((type(self), self.suit, self.number))

    def __eq__(self, other) -> bool:
        return hash(self) == hash(other)
