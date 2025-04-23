from __future__ import annotations
# stdlib
import re
import random
from typing import TYPE_CHECKING, Callable, Optional

# 3rd-party
import discord
from discord import app_commands
from discord.ext import commands

# 1st-party
from ..i18n import Msg, mkembed
from .protocol.engine import GameEngine
if TYPE_CHECKING:
    from ..lib.client import AbyxBot

TIMEOUT = 60.0
NUM_RE = re.compile('^[0-9]+$')

class NumguessEngine(GameEngine):

    secret: int
    last_guess: Optional[int] = None
    cur_min: int = 1
    cur_max: int = 100
    tries: int = 7

    def __init__(self, tries: int = 7) -> None:
        self.tries = tries
        self.secret = random.randint(self.cur_min, self.cur_max)

    def won(self) -> Optional[bool]:
        if self.last_guess == self.secret:
            return True
        if self.tries <= 0:
            return None
        return False

    def ended(self) -> bool:
        return self.won() is not None

    def update(self, guess: int) -> int:
        """Update the game state.

        guess: the new guess for the secret.
        Returns guess <=> secret, multiplied by 2 if out of bounds
        """
        self.last_guess = guess
        result = 0
        if guess <= self.cur_min:
            self.tries += 1 # undo for invalid input
            result = -2
        elif guess < self.secret:
            self.cur_min = guess
            result = -1
        elif guess >= self.cur_max:
            self.tries += 1
            result = +2
        elif guess > self.secret:
            self.cur_max = guess
            result = +1
        self.tries -= 1
        return result

class Numguess(commands.Cog):

    @app_commands.command()
    @app_commands.describe(tries='How many tries to give yourself. Default 7.')
    async def numguess(self, ctx: discord.Interaction,
                       tries: app_commands.Range[int, 0] = 7):
        """Play a number-guessing game!"""
        game = NumguessEngine(tries)
        await ctx.response.send_message(embed=self.gen_embed(ctx, game, None))
        while game.won() is False:
            guess_msg: discord.Message = await ctx.client.wait_for(
                'message', check=self.guess_check(ctx), timeout=TIMEOUT)
            guess = int(guess_msg.content)
            result = game.update(guess)
            await ctx.followup.send(embed=self.gen_embed(ctx, game, result))
        if game.won():
            await ctx.followup.send(embed=mkembed(ctx,
                title=Msg('numguess/ending-title'),
                description=Msg('numguess/won', game.tries),
                color=discord.Color.blurple()
            ))
        else:
            await ctx.followup.send(embed=mkembed(ctx,
                title=Msg('numguess/ending-title'),
                description=Msg('numguess/lost', game.secret),
                color=discord.Color.dark_red()
            ))

    def guess_check(self, ctx: discord.Interaction) -> Callable[[discord.Message], bool]:
        return lambda m: (
            ctx.channel is not None
            and m.channel.id == ctx.channel.id
            and bool(NUM_RE.match(m.content))
        )

    def gen_embed(self, ctx: discord.Interaction, game: NumguessEngine,
                  result: Optional[int]) -> discord.Embed:
        kwargs = dict(
            title=Msg('numguess/title'),
            fields=((Msg('numguess/min'), game.cur_min, True),
                    (Msg('numguess/max'), game.cur_max, True),
                    (Msg('numguess/tries'), game.tries, True)),
            footer=Msg('numguess/footer'),
            color=discord.Color.gold() if game.won() is False else 0x000001
        )
        if result is not None:
            # numguess/cmp:-2
            # numguess/cmp:-1
            # numguess/cmp:0
            # numguess/cmp:1
            # numguess/cmp:2
            kwargs['description'] = Msg(f'numguess/cmp:{result}')
        return mkembed(ctx, **kwargs)

async def setup(bot: AbyxBot):
    await bot.add_cog(Numguess())
