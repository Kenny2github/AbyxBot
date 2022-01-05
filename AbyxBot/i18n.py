# stdlib
import time
from typing import Any, Callable, Iterable, Optional, Union
import asyncio

# 3rd-party
import discord
from discord.abc import Snowflake
from discord.ext import slash

# 1st-party
from .load_i18n import load_i18n_strings, SUPPORTED_LANGS
from .chars import LABR, RABR
from .logger import get_logger
from .db import db

logger = get_logger('i18n')

IDContext = Union[slash.Context, discord.TextChannel, discord.User]

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
            return cls.user_langs.get(ctx.id) or default
        if isinstance(ctx, discord.TextChannel):
            return cls.channel_langs.get(ctx.id) or default
        if isinstance(ctx, discord.abc.Snowflake): # all you have is an ID
            return cls.user_langs.get(ctx.id) or \
                cls.channel_langs.get(ctx.id) or default
        return default

    @classmethod
    def load_strings(cls) -> None:
        """Load translation strings synchronously."""
        start = time.time()
        cls.unformatted.update(load_i18n_strings())
        end = time.time()
        logger.info('Loaded i18n strings in %.2f ms', (end - start) * 1000)

    @classmethod
    async def load_config(cls) -> None:
        """Load translation strings and user/channel language settings."""
        start = time.time()
        cls.user_langs.update(await db.user_langs())
        cls.channel_langs.update(await db.channel_langs())
        end = time.time()
        logger.info('Loaded i18n config cache in %.2f ms', (end - start) * 1000)

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

Msg.load_strings()

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

    def error_embed(self, error_message: Any, **kwargs) -> discord.Embed:
        return self.embed(
            Msg('error'), error_message,
            color=discord.Color.red()
        )

lang_opt = slash.Option(
    name='lang', description='The language to switch to.',
    choices=(slash.Choice(name=str(Msg('@name', lang=key)), value=key)
             # don't include the string documentation, but do include qqx;
             # sort languages here so that command definition updates
             # aren't triggered by differing choice orders
             for key in sorted(SUPPORTED_LANGS) if key != 'qqq'))

channel_opt = slash.Option(
    name='channel', description='The channel to configure languages for. \
By default, this is the one in which this command is run.',
    channel_type=discord.ChannelType.text)

class Internationalization:
    """i18n configuration commands"""

    @slash.group()
    async def lang(self, ctx: Context):
        """Get or set your command language, or that of a channel."""

    async def obj_get(self, ctx: Context, obj: Snowflake,
                      repo: dict[int, str], key1: str, key2: str) -> None:
        """Centralized user- or channel-language getter."""
        if repo.get(obj.id) is None:
            await ctx.respond(embed=ctx.embed(
                description=Msg(key2, obj.mention),
                color=discord.Color.red()
            ))
        else:
            await ctx.respond(embed=ctx.embed(
                description=Msg(key1, repo[obj.id], obj.mention),
                color=discord.Color.blue()
            ))

    async def obj_set(self, ctx: Context, obj: Snowflake,
                      repo: dict[int, str], value: str, key: str,
                      method: Callable[[int, Optional[str]], None]) -> None:
        """Centralized user- or channel-language setter."""
        repo[obj.id] = value
        asyncio.create_task(method(obj.id, value))
        await ctx.respond(embed=ctx.embed(
            description=Msg(key, value, obj.mention),
            color=discord.Color.blue()
        ))

    async def obj_reset(self, ctx: Context, obj: Snowflake,
                        repo: dict[int, str], key: str,
                        method: Callable[[int, Optional[str]], None]) -> None:
        """Centralized user- or channel-language resetter."""
        repo[obj.id] = None
        asyncio.create_task(method(obj.id, None))
        await ctx.respond(embed=ctx.embed(
            description=Msg(key, obj.mention),
            color=discord.Color.blue()
        ))

    @lang.slash_cmd(name='get')
    async def user_get(self, ctx: Context):
        """Get your command language."""
        await self.obj_get(ctx, ctx.author, Msg.user_langs,
                           'i18n/lang-get', 'i18n/lang-get-null')

    @lang.slash_cmd(name='set')
    async def user_set(self, ctx: Context, user_lang: lang_opt):
        """Set your command language."""
        await self.obj_set(ctx, ctx.author, Msg.user_langs, user_lang,
                           'i18n/lang-set', db.set_user_lang)

    @lang.slash_cmd(name='reset')
    async def user_reset(self, ctx: Context):
        """Reset your command language."""
        await self.obj_reset(ctx, ctx.author, Msg.user_langs,
                             'i18n/lang-reset', db.set_user_lang)

    @lang.slash_group()
    async def channel(self, ctx: Context):
        """Get or set the command language of a channel."""

    @channel.check
    async def channel_check(self, ctx: Context):
        """Ensure channel configurers have permission to do so."""
        set_channel = ctx.options.get('set_channel', ctx.channel)
        if not set_channel.permissions_for(ctx.author).manage_channels:
            await ctx.respond(embed=ctx.error_embed(
                Msg('i18n/lang-channel-noperms', set_channel.mention)
            ), ephemeral=True)
            return False
        return True

    @channel.slash_cmd(name='get')
    async def channel_get(self, ctx: Context,
                          set_channel: channel_opt = None):
        """Get your command language."""
        await self.obj_get(
            ctx, set_channel or ctx.channel, Msg.channel_langs,
            'i18n/lang-channel-get', 'i18n/lang-channel-get-null')

    @channel.slash_cmd(name='set')
    async def channel_set(self, ctx: Context, channel_lang: lang_opt,
                          set_channel: channel_opt = None):
        """Set your command language."""
        await self.obj_set(
            ctx, set_channel or ctx.channel, Msg.channel_langs,
            channel_lang, 'i18n/lang-channel-set', db.set_channel_lang)

    @channel.slash_cmd(name='reset')
    async def channel_reset(self, ctx: Context,
                            set_channel: channel_opt = None):
        """Reset your command language."""
        await self.obj_reset(
            ctx, set_channel or ctx.channel, Msg.channel_langs,
            'i18n/lang-channel-reset', db.set_channel_lang)

async def setup(bot: slash.SlashBot):
    bot.add_slash_cog(Internationalization())
    await Msg.load_config()
