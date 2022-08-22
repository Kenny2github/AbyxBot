# stdlib
import time
from logging import getLogger
from typing import Any, Callable, Coroutine, Iterable, Optional, TypeVar, Union, get_args
import asyncio

# 3rd-party
import discord
from discord import app_commands
from discord.ext import commands

# 1st-party
from .type_hints import ChannelLike, Mentionable, NamespaceChannel
from .load_i18n import load_i18n_strings, SUPPORTED_LANGS
from .chars import LABR, RABR
from .database import db

logger = getLogger(__name__)

IDContext = Union[discord.Interaction, Mentionable]
DBMethod = Callable[[int, Optional[str]], Coroutine[Any, Any, None]]

class Msg:
    """An i18n message.

    This can be initialized with a language code or a context from
    which to get it, like a discord.Interaction or discord.User or channel.

    Or it can be lazily initialized (preferred when being directly
    instantiated) and have its language set by other functions
    in this module.
    """

    # class attributes
    unformatted: dict[str, dict[str, str]] = {} # unformatted message strings
    user_langs: dict[int, Optional[str]] = {} # user language settings
    channel_langs: dict[int, Optional[str]] = {} # channel language settings

    # instance attributes
    key: str # i18n key
    params: tuple[str] # {0}, {1}, etc
    kwparams: dict[str, str] # {param}, {another}, etc
    lang: Optional[str] = None # can be set later
    # only set on init if lang is provided
    # otherwise, set upon str() casting
    message: Optional[str] = None

    @classmethod
    def get_lang(cls, ctx: Optional[discord.abc.Snowflake],
                 default: str = 'en') -> str:
        """Get the correct language for the context."""
        if isinstance(ctx, discord.Interaction):
            lang = ctx.locale.value
            if lang not in cls.unformatted:
                lang, _ = lang.split('-')
                if lang not in cls.unformatted:
                    lang = default
            return cls.get_lang(ctx.user, cls.get_lang(ctx.channel, lang))
        if isinstance(ctx, discord.abc.User):
            return cls.user_langs.get(ctx.id) or default
        if isinstance(ctx, (discord.abc.GuildChannel, discord.Thread)):
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
        *params,
        lang: Union[str, IDContext, None] = None,
        **kwparams
    ):
        if lang is None:
            pass
        elif isinstance(lang, str):
            self.lang = lang
        elif isinstance(lang, get_args(IDContext)):
            self.lang = self.get_lang(lang)
        else:
            raise TypeError(f'unexpected {type(lang).__name__!r} for "lang"')
        self.key = key
        self.params = tuple(map(str, params))
        self.kwparams = {k: str(v) for k, v in kwparams.items()}
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
            assert self.message is not None
        return self.message.format(*self.params, **self.kwparams)

    def set_message(self) -> None:
        """Load the unformatted message from language information."""
        if self.lang is None:
            raise RuntimeError('Cannot set message when lang not set')
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

def cast(ctx: IDContext, /, msg: Any) -> str:
    """If msg is a message object, format and return it.
    Otherwise, cast it to a string in the usual manner.
    """
    if isinstance(msg, Msg):
        msg.lang = msg.get_lang(ctx)
    return str(msg)

def mkmsg(ctx: IDContext, /, key: str, *params, **kwparams):
    """Format a message in this context."""
    if isinstance(ctx, (str, Msg)):
        raise TypeError(f'Unexpected {type(ctx).__name__!r} for ctx. '
                        'Did you forget to pass it?')
    return str(Msg(key, *params, **kwparams, lang=ctx))

def mkembed(
    ctx: IDContext, /,
    title: Any = None,
    description: Any = None,
    fields: Iterable[tuple[Any, Any, bool]] = (),
    footer: Any = None,
    **kwargs
) -> discord.Embed:
    """Construct an Embed with messages or strings"""
    if isinstance(ctx, (str, Msg)):
        raise TypeError(f'Unexpected {type(ctx).__name__!r} for ctx. '
                        'Did you forget to pass it?')
    if title:
        kwargs['title'] = cast(ctx, title)
    if description:
        kwargs['description'] = cast(ctx, description)
    embed = discord.Embed(**kwargs)
    if footer:
        embed.set_footer(text=cast(ctx, footer))
    for name, value, inline in fields or ():
        embed.add_field(
            name=cast(ctx, name),
            value=cast(ctx, value),
            inline=inline
        )
    return embed

def error_embed(ctx: IDContext, error_message: Any, **kwargs) -> discord.Embed:
    return mkembed(ctx,
        Msg('error'), error_message,
        color=discord.Color.red(), **kwargs
    )

T = TypeVar('T', bound=Callable)

def lang_opt(func: T) -> T:
    return app_commands.describe(
        lang='The language to switch to.'
    )(app_commands.choices(lang=[
        app_commands.Choice(name=str(Msg('@name', lang=key)), value=key)
        # don't include the string documentation, but do include qqx;
        # sort languages here so that command definition updates
        # aren't triggered by differing choice orders
        for key in sorted(SUPPORTED_LANGS) if key != 'qqq'
    ]))(func)

def channel_opt(func: T) -> T:
    return app_commands.describe(
        channel='The channel to configure languages for. \
By default, this is the one in which this command is run.'
    )(func)

class _I18n:
    """Static obj_x methods."""

    async def obj_get(self, ctx: discord.Interaction, obj: Mentionable,
                      repo: dict[int, Optional[str]],
                      key1: str, key2: str) -> None:
        """Centralized user- or channel-language getter."""
        if repo.get(obj.id) is None:
            await ctx.response.send_message(embed=mkembed(ctx,
                description=Msg(key2, obj.mention),
                color=discord.Color.red()
            ))
        else:
            await ctx.response.send_message(embed=mkembed(ctx,
                description=Msg(key1, repo[obj.id], obj.mention),
                color=discord.Color.blue()
            ))

    async def obj_set(self, ctx: discord.Interaction, obj: Mentionable,
                      repo: dict[int, Optional[str]], value: str, key: str,
                      method: DBMethod) -> None:
        """Centralized user- or channel-language setter."""
        repo[obj.id] = value
        asyncio.create_task(method(obj.id, value))
        await ctx.response.send_message(embed=mkembed(ctx,
            description=Msg(key, value, obj.mention),
            color=discord.Color.blue()
        ))

    async def obj_reset(self, ctx: discord.Interaction, obj: Mentionable,
                        repo: dict[int, Optional[str]], key: str,
                        method: DBMethod) -> None:
        """Centralized user- or channel-language resetter."""
        repo[obj.id] = None
        asyncio.create_task(method(obj.id, None))
        await ctx.response.send_message(embed=mkembed(ctx,
            description=Msg(key, obj.mention),
            color=discord.Color.blue()
        ))

class ChannelI18n(app_commands.Group, _I18n):
    """Get or set the command language of a channel."""

    def __init__(self, **kwargs):
        super().__init__(name='channel', **kwargs)

    async def interaction_check(self, ctx: discord.Interaction):
        """Ensure channel configurers have permission to do so."""
        arg: Optional[ChannelLike] = ctx.namespace.channel
        channel = arg or ctx.channel
        if isinstance(channel, NamespaceChannel):
            channel = channel.resolve()
        if channel is None:
            return False # if we can't get a channel, assume no perms
        if isinstance(channel, discord.PartialMessageable) \
                or not isinstance(ctx.user, discord.Member):
            return False # if we're in a DM, fail
        if not channel.permissions_for(ctx.user).manage_channels:
            await ctx.response.send_message(embed=error_embed(ctx,
                Msg('i18n/lang-channel-noperms', channel.mention)
            ), ephemeral=True)
            return False
        return True

    @app_commands.command()
    @channel_opt
    async def get(self, ctx: discord.Interaction,
                  channel: Optional[ChannelLike] = None):
        """Get your command language."""
        await self.obj_get(
            ctx, channel or ctx.channel, # type: ignore - checks exclude None
            Msg.channel_langs, 'i18n/lang-channel-get',
            'i18n/lang-channel-get-null')

    @app_commands.command()
    @channel_opt
    @lang_opt
    async def set(self, ctx: discord.Interaction, lang: str,
                  channel: Optional[ChannelLike] = None):
        """Set your command language."""
        await self.obj_set(
            ctx, channel or ctx.channel, # type: ignore - ditto
            Msg.channel_langs, lang, 'i18n/lang-channel-set',
            db.set_channel_lang)

    @app_commands.command(name='reset')
    @channel_opt
    async def channel_reset(
        self, ctx: discord.Interaction,
        channel: Optional[ChannelLike] = None
    ):
        """Reset your command language."""
        await self.obj_reset(
            ctx, channel or ctx.channel, # type: ignore - ditto
            Msg.channel_langs, 'i18n/lang-channel-reset', db.set_channel_lang)

class Internationalization(app_commands.Group, _I18n):
    """Get or set your command language, or that of a channel."""

    def __init__(self, **kwargs):
        super().__init__(name='lang', **kwargs)

    @app_commands.command(name='get')
    async def user_get(self, ctx: discord.Interaction):
        """Get your command language."""
        await self.obj_get(ctx, ctx.user, Msg.user_langs,
                           'i18n/lang-get', 'i18n/lang-get-null')

    @app_commands.command(name='set')
    @lang_opt
    async def user_set(self, ctx: discord.Interaction, lang: str):
        """Set your command language."""
        await self.obj_set(ctx, ctx.user, Msg.user_langs, lang,
                           'i18n/lang-set', db.set_user_lang)

    @app_commands.command(name='reset')
    async def user_reset(self, ctx: discord.Interaction):
        """Reset your command language."""
        await self.obj_reset(ctx, ctx.user, Msg.user_langs,
                             'i18n/lang-reset', db.set_user_lang)

    channel_group = ChannelI18n()

async def setup(bot: commands.Bot):
    bot.tree.add_command(Internationalization())
    await Msg.load_config()
