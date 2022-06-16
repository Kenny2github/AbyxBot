# stdlib
import random
from typing import Optional

# 3rd-party
import discord
from discord import app_commands
from discord.ext import commands

# 1st-party
from ..chars import UP, DOWN, LEFT, RIGHT
from ..database import db
from ..i18n import Msg, error_embed, mkembed
from ..utils import str_to_emoji
from .protocol.engine import GameEngine

TWO_CHANCE = 0.9
TIMEOUT = 60.0

ARROWS: dict[str, tuple[int, int]] = {
    LEFT: (0, -1),
    UP: (-1, 0),
    DOWN: (1, 0),
    RIGHT: (0, 1),
}

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

class Engine2048(GameEngine):

    points: int
    board: list[list[Optional[int]]]
    ending: int = 2048
    allow_continue: bool = False

    def __init__(self, ending: int = 2048,
                 allow_continue: bool = False) -> None:
        self.ending = ending
        self.allow_continue = allow_continue
        self.points = 0
        self.board = [[None] * 4 for _ in range(4)]
        self.add_random_tile()
        self.add_random_tile()

    def game_done(self) -> bool:
        """Has the game ended?"""
        return self.won() is not False

    def has_legal_move(self) -> bool:
        for x in range(4):
            for y in range(4):
                if self.board[x][y] is None:
                    return True # empty square = legal move
                if any((
                    x > 0 and self.board[x][y] == self.board[x-1][y],
                    x < 3 and self.board[x][y] == self.board[x+1][y],
                    y > 0 and self.board[x][y] == self.board[x][y-1],
                    y < 3 and self.board[x][y] == self.board[x][y+1],
                )):
                    return True # a legal move is possible
        return False

    def won(self, ignore_continue: bool = False) -> Optional[bool]:
        """Has the game ended by winning?

        Returns:
        * ``True`` for yes
        * ``None`` if the game has ended, but not by winning
        * ``False`` if the game has not yet ended
        """
        all_tiles = [tile for row in self.board for tile in row]
        if self.allow_continue and not ignore_continue:
            if self.has_legal_move():
                # any legal move under allow_continue = not done
                # though you may have already won
                return False
            if any(tile >= self.ending
                   for tile in all_tiles if tile is not None):
                # no legal moves and a tile is a winning tile
                return True
            return None # no legal moves and no tile won
        if any(tile >= self.ending for tile in all_tiles if tile is not None):
            # outside of allow_continue, any win is game end
            return True
        if self.has_legal_move():
            return False # legal moves and not won = not done
        return None # no legal moves and not won, so lost

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
        if x is None or y is None:
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

    def merge(self, xrange: list[int], yrange: list[int],
              dx: int, dy: int) -> bool:
        """Merge adjacent identical tiles."""
        moved = set()
        changed_once = False
        changed = True
        while changed:
            changed = False
            for x in xrange:
                for y in yrange:
                    if self.board[x][y] is None or (x, y) in moved:
                        continue
                    if self.board[x][y] == self.board[x+dx][y+dy]:
                        value = self.board[x+dx][y+dy]
                        if value is None:
                            continue
                        value *= 2
                        self.board[x+dx][y+dy] = value
                        self.board[x][y] = None
                        self.points += value
                        changed = changed_once = True
                        moved.add((x + dx, y + dy))
                        moved.add((x, y))
        return changed_once

    def fall(self, xrange: list[int], yrange: list[int],
             dx: int, dy: int) -> bool:
        """Fall to one side."""
        changed_once = False
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
                        changed = changed_once = True
        return changed_once

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
        changed_once = False
        changed = True
        while changed:
            changed = False
            changed = changed or self.fall(xrange, yrange, dx, dy)
            changed = changed or self.merge(xrange, yrange, dx, dy)
            changed_once = changed_once or changed
        if changed_once:
            self.add_random_tile()
        return self.game_done()

class ArrowView(discord.ui.View):
    def __init__(self, author_id: int, highscore: int, game: Engine2048):
        super().__init__(timeout=TIMEOUT)
        for arrow, (dx, dy) in ARROWS.items():
            self.add_item(ArrowButton(arrow, dx, dy))
        self.author_id = author_id
        self.highscore = highscore
        self.game = game
        self.last_ctx = None
        self.victory_notified = False

    async def interaction_check(self, ctx: discord.Interaction) -> bool:
        self.last_ctx = ctx
        return ctx.user.id == self.author_id

    async def on_timeout(self) -> None:
        assert self.last_ctx is not None
        await self.last_ctx.edit_original_message(view=None)
        await self.last_ctx.followup.send(embed=error_embed(
            self.last_ctx, Msg('2048/timeout')))

    async def update_state(self, ctx: discord.Interaction,
                           dx: int, dy: int) -> None:
        self.last_ctx = ctx
        game_done = self.game.update(dx, dy)
        if game_done:
            await ctx.response.edit_message(
                embed=self.gen_embed(ctx), view=None)
            await self.conclude(ctx)
        else:
            await ctx.response.edit_message(embed=self.gen_embed(ctx))
            if not self.victory_notified \
                    and self.game.won(ignore_continue=True):
                self.victory_notified = True
                await ctx.followup.send(embed=mkembed(ctx,
                    Msg('2048/won-continue-title'),
                    Msg('2048/won-continue', self.game.ending),
                    color=discord.Color.green()
                ))

    async def conclude(self, ctx: discord.Interaction):
        self.last_ctx = ctx
        if self.game.points > self.highscore:
            await ctx.followup.send(embed=mkembed(ctx,
                Msg('2048/highscore-title'),
                Msg('2048/highscore', self.game.points),
                color=discord.Color.blurple()
            ))
        if self.game.won():
            await ctx.followup.send(embed=mkembed(ctx,
                Msg('2048/gg'), Msg('2048/won', self.game.points, self.game.ending),
                color=discord.Color.green()
            ))
        else:
            await ctx.followup.send(embed=mkembed(ctx,
                Msg('2048/gg'), Msg('2048/lost', self.game.points),
                color=discord.Color.red()
            ))
        self.stop()

    def gen_embed(self, ctx: discord.Interaction) -> discord.Embed:
        self.last_ctx = ctx
        return mkembed(ctx,
            Msg('2048/embed-title'), self.game.board_to_text(),
            fields=((Msg('2048/points-title'), Msg(
                '2048/points', self.game.points, self.highscore), False),),
            footer=Msg('2048/footer'), color=discord.Color.gold()
        )

class ArrowButton(discord.ui.Button[ArrowView]):

    def __init__(self, arrow: str, dx: int, dy: int):
        super().__init__(
            style=discord.ButtonStyle.primary,
            emoji=str_to_emoji(arrow),
            custom_id=f'{dx}:{dy}'
        )
        self.dx, self.dy = dx, dy

    async def callback(self, ctx: discord.Interaction) -> None:
        assert self.view is not None
        await self.view.update_state(ctx, self.dx, self.dy)

class Pow211(commands.Cog):

    @app_commands.command(name='2048')
    @app_commands.describe(
        ending='The power of 2 to end at. Default 11 '
        '(2**11=2048, the name of the game).',
        allow_continue='Whether to keep playing after you reach the end. '
        'Default False (no).'
    )
    async def pow211(self, ctx: discord.Interaction,
                     ending: app_commands.Range[int, 4] = 11,
                     allow_continue: bool = False):
        """Play 2048!"""
        game = Engine2048(1 << ending, allow_continue)
        highscore = await db.get_2048_highscore(ctx.user.id)
        view = ArrowView(ctx.user.id, highscore, game)
        await ctx.response.send_message(
            embed=view.gen_embed(ctx), view=view)

        try:
            await view.wait()
        finally:
            if not view.is_finished():
                view.stop()
            if game.points > highscore:
                await db.set_2048_highscore(ctx.user.id, game.points)

async def setup(bot: commands.Bot):
    await bot.add_cog(Pow211())
