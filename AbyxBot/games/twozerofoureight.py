# stdlib
import random
import asyncio
from typing import Optional

# 3rd-party
from discord.ext import slash

TWO_CHANCE = 0.9

LEFT = '\N{LEFTWARDS BLACK ARROW}'
RIGHT = '\N{BLACK RIGHTWARDS ARROW}'
UP = '\N{UPWARDS BLACK ARROW}'
DOWN = '\N{DOWNWARDS BLACK ARROW}'
ARROWS = LEFT, RIGHT, UP, DOWN

HORI = '\N{BOX DRAWINGS LIGHT HORIZONTAL}'
LEFTSIDE = '\N{BOX DRAWINGS VERTICAL DOUBLE AND RIGHT SINGLE}'
RIGHTSIDE = '\N{BOX DRAWINGS VERTICAL DOUBLE AND LEFT SINGLE}'
JOINT = '\N{BOX DRAWINGS LIGHT VERTICAL AND HORIZONTAL}'
TOPLEFT = '\N{BOX DRAWINGS DOUBLE DOWN AND RIGHT}'
DBL = '\N{BOX DRAWINGS DOUBLE HORIZONTAL}'
TOPSIDE = '\N{BOX DRAWINGS DOWN SINGLE AND HORIZONTAL DOUBLE}'
TOPRIGHT = '\N{BOX DRAWINGS DOUBLE DOWN AND LEFT}'
BOTLEFT = '\N{BOX DRAWINGS DOUBLE UP AND RIGHT}'
BOTSIDE = '\N{BOX DRAWINGS UP SINGLE AND HORIZONTAL DOUBLE}'
BOTRIGHT = '\N{BOX DRAWINGS DOUBLE UP AND LEFT}'
VERT = '\N{BOX DRAWINGS LIGHT VERTICAL}'
DBLV = '\N{BOX DRAWINGS DOUBLE VERTICAL}'

Board = list[list[Optional[int]]]

class Game:

    points: int
    board: Board

    def __init__(self) -> None:
        self.points = 0
        self.board = [[None] * 4 for _ in range(4)]
        self.add_random_tile()
        self.add_random_tile()

    def game_done(self) -> bool:
        """Has the game ended?"""
        for row in self.board:
            for tile in row:
                if tile == 2048:
                    return True # ended by winning!
                if tile is None:
                    return False
        # no empty squares, but maybe we can still move?
        for x in range(4):
            for y in range(4):
                if any((
                    x > 0 and self.board[x][y] == self.board[x-1][y],
                    x < 4 and self.board[x][y] == self.board[x+1][y],
                    y > 0 and self.board[x][y] == self.board[x][y-1],
                    y < 4 and self.board[x][y] == self.board[x][y+1],
                )):
                    return False # a legal move is possible
        # no legal moves are possible
        return True

    def random_space(self) -> tuple[Optional[int], Optional[int]]:
        """Choose a random empty space on the board."""
        choices: list[tuple[int, int]] = []
        for x in range(4):
            for y in range(4):
                if self.board[x][y] is None:
                    choices.append((x, y))
        try:
            return random.choice(choices)
        except IndexError:
            return None, None

    def add_random_tile(self) -> None:
        """Add a tile to a random empty space on the board."""
        new_value = 2 if random.random() < TWO_CHANCE else 4
        x, y = self.random_space()
        if x is None:
            return # failed to add tile
        self.board[x][y] = new_value

    def board_to_text(self) -> str:
        """Convert the board into a format suitable for display on Discord."""
        # intra-row border
        row_sep = f'\n{LEFTSIDE}{HORI*4}{(JOINT+HORI*4)*3}{RIGHTSIDE}\n'
        top_border = f'{TOPLEFT}{DBL*4}{(TOPSIDE+DBL*4)*3}{TOPRIGHT}\n'
        rows = row_sep.join(DBLV + VERT.join(
            str(tile or '').center(4) for tile in row
        ) + DBLV for row in self.board)
        bottom_border = f'\n{BOTLEFT}{DBL*4}{(BOTSIDE+DBL*4)*3}{BOTRIGHT}'
        return f'```\n{top_border + rows + bottom_border}\n```'

    def update(self, dx: int, dy: int) -> bool:
        """Update the game state.

        dx, dy: the direction to fall and merge in.
        Returns whether the game is over.
        """
        di = dx or dy
        assert not (dx and dy) and di
        if dx > 0:
            xrange = list(range(2, -1, -1))
        elif dx < 0:
            xrange = list(range(1, 4))
        else:
            xrange = list(range(4))
        if dy > 0:
            yrange = list(range(2, -1, -1))
        elif dy < 0:
            yrange = list(range(1, 4))
        else:
            yrange = list(range(4))
        # fall
        changed = True
        while changed:
            changed = False
            for x in xrange:
                for y in yrange:
                    if self.board[x][y] is None:
                        #   v
                        # 1 0 1 1
                        continue
                    if self.board[x+dx][y+dy] is None:
                        #     v        v
                        # 1 0 1 => 1 1 0
                        self.board[x+dx][y+dy] = self.board[x][y]
                        self.board[x][y] = None
                        changed = True
        # merge
        moved = set()
        changed = True
        while changed:
            changed = False
            for x in xrange:
                for y in yrange:
                    if self.board[x][y] is None or (x, y) in moved:
                        continue
                    if self.board[x][y] == self.board[x+dx][y+dy]:
                        self.board[x+dx][y+dy] *= 2
                        self.board[x][y] = None
                        self.points += self.board[x+dx][y+dy]
                        changed = True
                        moved.add((x + dx, y + dy))
                        moved.add((x, y))
        self.add_random_tile()

class Pow211:

    @slash.cmd(name='2048')
    async def pow211(self, ctx: slash.Context):
        """Play 2048!"""

if __name__ == '__main__':
    game = Game()