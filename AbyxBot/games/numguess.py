# stdlib
import re
import random
from typing import Callable, Optional

# 3rd-party
import discord
from discord.ext import slash

# 1st-party
from ..i18n import Context, Msg
from .protocol.engine import GameEngine

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

tries_opt = slash.Option(
    'How many tries to give yourself. Default 7.',
    min_value=0)

class Numguess:

    @slash.cmd()
    async def numguess(self, ctx: Context, tries: tries_opt = 7):
        """Play a number-guessing game!"""
        game = NumguessEngine(tries)
        await ctx.respond(embed=self.gen_embed(ctx, game, None))
        while game.won() is False:
            guess_msg: discord.Message = await ctx.bot.wait_for(
                'message', check=self.guess_check(ctx), timeout=TIMEOUT)
            guess = int(guess_msg.content)
            result = game.update(guess)
            await ctx.webhook.send(embed=self.gen_embed(ctx, game, result))
        if game.won():
            await ctx.webhook.send(embed=ctx.embed(
                title=Msg('numguess/ending-title'),
                description=Msg('numguess/won', game.tries),
                color=discord.Color.blurple()
            ))
        else:
            await ctx.webhook.send(embed=ctx.embed(
                title=Msg('numguess/ending-title'),
                description=Msg('numguess/lost', game.secret),
                color=discord.Color.dark_red()
            ))

    def guess_check(self, ctx: Context) -> Callable[[discord.Message], bool]:
        return lambda m: (
            m.channel.id == ctx.channel.id
            and NUM_RE.match(m.content)
        )

    def gen_embed(self, ctx: Context, game: NumguessEngine,
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
        return ctx.embed(**kwargs)

def setup(bot: slash.SlashBot):
    bot.add_slash_cog(Numguess())