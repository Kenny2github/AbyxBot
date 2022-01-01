from __future__ import annotations
import os
import time
import json
from typing import Any, Iterable, Optional, Union
import aiofiles
import discord
from discord.ext import slash
from .chars import LABR, RABR
from .logger import get_logger
from .db import db

ROOT = 'i18n'
SUPPORTED_LANGS = set(
    fn[:-5] for fn in os.listdir(ROOT) if fn.endswith('.json'))

logger = get_logger('i18n')

class Msg:
    """An i18n message.

    This can be initialized with a language code or a context from
    which to get it, like a slash.Context or discord.User or channel.

    Or it can be lazily initialized (preferred when being directly
    instantiated) and have its language set by other functions
    in this module.
    """

    # class attributes
    unformatted: dict[str, dict[str, str]] = {} # unformatted message strings
    user_langs: dict[int, str] = {} # user language settings
    channel_langs: dict[int, str] = {} # channel language settings

    # instance attributes
    key: str # i18n key
    params: tuple[str] # {0}, {1}, etc
    kwparams: dict[str, str] # {param}, {another}, etc
    lang: Optional[str] = None # can be set later
    # only set on init if lang is provided
    # otherwise, set upon str() casting
    message: Optional[str] = None

    @classmethod
    def get_lang(cls, ctx: IDContext, default: str = 'en') -> str:
        """Get the correct language for the context."""
        if isinstance(ctx, slash.Context):
            return cls.get_lang(ctx.author, cls.get_lang(ctx.channel))
        if isinstance(ctx, discord.User):
            return cls.user_langs.get(ctx.id, default)
        if isinstance(ctx, discord.TextChannel):
            return cls.channel_langs.get(ctx.id, default)
        if isinstance(ctx, discord.abc.Snowflake): # all you have is an ID
            return cls.user_langs.get(
                ctx.id, cls.channel_langs.get(ctx.id, default))
        return default

    @classmethod
    async def load_state(cls) -> None:
        """Load translation strings and user/channel language settings."""
        start = time.time()
        for lang in SUPPORTED_LANGS:
            async with aiofiles.open(os.path.join(ROOT, f'{lang}.json')) as f:
                data: dict = json.loads(await f.read())
            cls.unformatted.setdefault(lang, {}).update(data)
        for dirname in os.listdir(ROOT):
            if not os.path.isdir(os.path.join(ROOT, dirname)):
                continue # now dirname is an actual dir name
            for lang in SUPPORTED_LANGS:
                path = os.path.join(ROOT, dirname, f'{lang}.json')
                try:
                    async with aiofiles.open(path) as f:
                        data: dict = json.loads(await f.read())
                except FileNotFoundError:
                    if lang != 'qqx': # qqx only needs one file
                        logger.warning('No %s i18n for %s/', lang, dirname)
                    continue
                for key, string in data.items():
                    cls.unformatted[lang][f'{dirname}/{key}'] = string
        cls.user_langs.update(await db.user_langs())
        cls.channel_langs.update(await db.channel_langs())
        end = time.time()
        logger.info('Loaded i18n cache in %.2f ms', (end - start) * 1000)

    def __init__(
        self,
        key: str,
        *params: str,
        lang: Union[str, IDContext, None] = None,
        **kwparams: str
    ):
        if lang is None:
            pass
        elif isinstance(lang, str):
            self.lang = lang
        elif isinstance(lang, (slash.Context, discord.TextChannel, discord.User)):
            self.lang = self.get_lang(lang)
        else:
            raise TypeError(f'unexpected {type(lang).__name__!r} for "lang"')
        self.key = key
        self.params = params
        self.kwparams = kwparams
        if self.lang is not None:
            self.set_message()

    def __repr__(self) -> str:
        """Barebones representation of the object."""
        params = ', '.join(map(repr, self.params))
        kwparams = ', '.join(f'{kw}={param!r}'
                             for kw, param in self.kwparams.items())
        return f'Msg({self.key!r}, {params}, lang={self.lang!r}, {kwparams})'

    def __str__(self) -> str:
        """Format the message and return it for use."""
        if self.message is None:
            if self.lang is None:
                return repr(self)
            self.set_message()
        return self.message.format(*self.params, **self.kwparams)

    def set_message(self) -> None:
        """Load the unformatted message from language information."""
        if self.lang == 'qqx':
            self.message = f'({self.default()})'
        else:
            self.message = self.unformatted[self.lang].get(self.key)
            if self.message is None:
                logger.debug('no %s string set for %r', self.lang, self.key)
                self.message = self.unformatted['en'].get(self.key)
            if self.message is None:
                logger.warning('no en string set for %r', self.key)
                self.message = LABR + self.default() + RABR

    def default(self) -> str:
        """Fallback message (without brackets) if no string is set."""
        # format: (key): {0}, {1}, param={param}, another={another}
        # when .format()ted, becomes (key): p0, p1, param=p2, another=p3
        result = self.key
        if self.params or self.kwparams:
            result += ': '
        if self.params:
            result += ', '.join('{%s}' % i for i in range(len(self.params)))
        if self.kwparams:
            if self.params:
                result += ', ' # separate positional and keyword
            result += ', '.join('%s={%s}' % (key, key)
                                for key in self.kwparams.keys())
        return result

class Context(slash.Context):

    def cast(self, msg: Any) -> str:
        """If msg is a message object, format and return it.
        Otherwise, cast it to a string in the usual manner.
        """
        if isinstance(msg, Msg):
            msg.lang = msg.get_lang(self)
        return str(msg)

    def msg(self, key: str, *params: str, **kwparams: str):
        """Format a message in this context."""
        return str(Msg(key, *params, **kwparams, lang=self))

    def embed(
        self,
        title: Any = None,
        description: Any = None,
        fields: Iterable[tuple[Any, Any, bool]] = (),
        footer: Any = None,
        **kwargs
    ) -> discord.Embed:
        """Construct an Embed with messages or strings"""
        if title:
            kwargs['title'] = self.cast(title)
        if description:
            kwargs['description'] = self.cast(description)
        embed = discord.Embed(**kwargs)
        if footer:
            embed.set_footer(text=self.cast(footer))
        for name, value, inline in fields or ():
            embed.add_field(
                name=self.cast(name),
                value=self.cast(value),
                inline=inline
            )
        return embed

IDContext = Union[slash.Context, discord.TextChannel, discord.User]

def setup(bot: slash.SlashBot):
    bot.loop.run_until_complete(Msg.load_state())