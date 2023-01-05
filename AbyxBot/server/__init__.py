# stdlib
from contextlib import asynccontextmanager
import time
from secrets import token_bytes, token_hex
from logging import getLogger
from pathlib import Path
from typing import (
    AsyncIterator, TypedDict, NoReturn, Callable, Optional
)
from urllib.parse import urlencode, urlparse
import asyncio

# 3rd-party
from aiohttp import ClientSession, web
from aiohttp_jinja2 import setup as setup_jinja2, template
import jinja2
from aiohttp_session import setup as setup_session, get_session as _get_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from async_lru import alru_cache
import discord

# 1st-party
from ..consts.config import config
from ..i18n import mkmsg, Msg, SUPPORTED_LANGS
from ..lib.database import db

DISCORD_API = 'https://discord.com/api/v10'
DISCORD_OAUTH2 = 'https://discord.com/oauth2/authorize'
DISCORD_TOKEN = 'https://discord.com/api/oauth2/token'
CLIENT_ID: int = config.client_id
CLIENT_SECRET: str = config.client_secret
WEB_ROOT: str = config.web_root
REDIRECT_URI: str = WEB_ROOT + '/api/oauth2/callback'
SCOPES = 'identify guilds'
TOKEN_TYPE = 'Bearer'

logger = getLogger(__name__)

class TokenResponse(TypedDict):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    scope: str

class SessionData(TypedDict):
    # oauth stuff
    return_to: str
    state: str
    access_token: str
    expiry: float
    refresh_token: str

    # cached for i18n
    user_id: int

class GuildDict(TypedDict):
    id: str
    name: str
    icon: str
    owner: bool
    permissions: str
    features: list[str]

class ChannelSettings(TypedDict, total=False):
    lang: str

class GuildSettings(TypedDict, total=False):
    words_censor: str
    channels: dict[str, ChannelSettings]

async def get_session(request: web.Request) -> SessionData:
    """Passthru for type casting"""
    return await _get_session(request) # type: ignore

def acronym(name: str) -> str:
    """Turn a name into an acronym from the first character of each word."""
    return ''.join(word[0] for word in name.split() if word)

@alru_cache()
async def fetch_guilds_cached(
    session: ClientSession, token: str,
) -> list[GuildDict]:
    headers = {'Authorization': f'Bearer {token}'}
    async with session.get(
        DISCORD_API + '/users/@me/guilds',
        headers=headers,
    ) as resp:
        resp.raise_for_status()
        return await resp.json()

class Handler:
    """Request handler class for the server."""

    def __init__(self, bot: discord.Client) -> None:
        self.app = web.Application()
        self.bot = bot

        # set up Jinja2
        setup_jinja2(
            self.app, loader=jinja2.FileSystemLoader(
                [Path(__file__).parent / 'templates']),
            trim_blocks=True, lstrip_blocks=True,
            autoescape=jinja2.select_autoescape())

        # set up sessions
        if config.session_key:
            key = bytes(config.session_key)
        else:
            key = token_bytes()
        setup_session(self.app, EncryptedCookieStorage(key, samesite='Lax'))

        # set up OAuth2
        self.app.add_routes([
            web.get('/api/oauth2/auth', self.oauth2_auth),
            web.get('/api/oauth2/callback', self.oauth2_callback),
        ])

        # set up view routes
        self.app.add_routes([
            web.static('/static/', Path(__file__).parent / 'static'),
            web.get('/', self.index),
            web.get('/settings', self.get_settings),
            web.post('/settings', self.post_settings),
            web.get('/servers', self.servers),
            web.get(r'/servers/{id:\d+}', self.get_server),
            web.patch(r'/servers/{id:\d+}', self.patch_server),
        ])

        self.user_cache: dict[int, dict] = {}

        self.session = ClientSession()
        self.runner = web.AppRunner(self.app)

    async def start(self) -> None:
        await self.runner.setup()
        web_root = urlparse(WEB_ROOT)
        site = web.TCPSite(self.runner, web_root.hostname, web_root.port)
        logger.info('Starting on %s', WEB_ROOT)
        await site.start()

    async def stop(self) -> None:
        await self.runner.cleanup()
        await self.session.close()

    @asynccontextmanager
    async def run(self) -> AsyncIterator[None]:
        await self.start()
        try:
            yield
        finally:
            await self.stop()

    ### OAuth2 endpoints ###

    async def oauth2_auth(self, request: web.Request) -> NoReturn:
        """The endpoint that redirects to Discord authorization."""
        state = token_hex()
        session = await get_session(request)
        session['state'] = state
        url = DISCORD_OAUTH2 + '?' + urlencode({
            'response_type': 'code',
            'client_id': config.client_id,
            'scope': 'identify guilds',
            'state': state,
            'redirect_uri': REDIRECT_URI,
            'prompt': 'none',
        })
        logger.getChild('api.oauth2.auth').debug(
            'Redirecting %s to %s', request.remote, url)
        raise web.HTTPSeeOther(url)

    async def oauth2_callback(self, request: web.Request) -> NoReturn:
        """The endpoint that gets the token."""
        # check validity
        if 'code' not in request.query:
            raise web.HTTPBadRequest(text='Missing code')
        if 'state' not in request.query:
            raise web.HTTPBadRequest(text='Missing state')
        session = await get_session(request)
        if 'state' not in session:
            raise web.HTTPConflict(text='Not currently authorizing')

        code: str = request.query['code']
        state: str = request.query['state']
        if state != session['state']:
            raise web.HTTPBadRequest(text='Bad state')

        # get token
        async with self.session.post(DISCORD_TOKEN, data={
            'client_id': config.client_id,
            'client_secret': config.client_secret,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI,
        }) as resp:
            resp.raise_for_status()
            data: TokenResponse = await resp.json()

        # update session and redirect
        await self.set_oauth2(request, data)
        session = await get_session(request)
        return_to = session.get('return_to', '/')
        logger.getChild('api.oauth2.callback').debug(
            'Redirecting %s to %s', request.remote, return_to)
        raise web.HTTPTemporaryRedirect(return_to)

    ### discord API helpers ###

    async def get_user(self, request: web.Request) -> dict:
        """Get the logged in user from cache, or fetch if not cached."""
        session = await get_session(request)
        if session['user_id'] not in self.user_cache:
            logger.getChild('get_user').debug('User %s not cached, fetching',
                                              session['user_id'])
            return await self.fetch_user(request)
        return self.user_cache[session['user_id']]

    async def fetch_user(self, request: web.Request) -> dict:
        """Fetch the logged in user, overwriting cache."""
        session = await get_session(request)
        headers = {'Authorization': f"Bearer {session['access_token']}"}
        async with self.session.get(
            DISCORD_API + '/users/@me',
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            user = await resp.json()
        self.user_cache[int(user['id'])] = user
        return user

    async def fetch_guilds(self, request: web.Request) -> list[GuildDict]:
        """Fetch the logged in user's guilds."""
        session = await get_session(request)
        guilds: list[GuildDict] = await fetch_guilds_cached( # type: ignore
            self.session, session['access_token'])
        return [guild for guild in guilds
                # only include guilds we can access
                if self.bot.get_guild(int(guild['id'])) is not None]

    async def fetch_guild(self, request: web.Request) -> discord.Guild:
        """Fetch the guild being requested from the bot's guilds."""
        log = logger.getChild('fetch_guild')
        guild_id = int(request.match_info['id']) # route guarantees validity
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            log.warning('Guild %s cache miss', guild_id)
            try:
                guild = await self.bot.fetch_guild(guild_id)
            except discord.HTTPException as exc:
                log.exception('Failed to fetch guild %s', guild_id)
                raise web.HTTPNotFound from exc
        log.debug('Fetched guild %s', guild.id)
        return guild

    ### session helpers ###

    async def set_oauth2(self, request: web.Request,
                         token: TokenResponse) -> None:
        """Update OAuth2 cookie data."""
        session = await get_session(request)
        session['access_token'] = token['access_token']
        session['expiry'] = time.time() + token['expires_in'] - 1
        session['refresh_token'] = token['refresh_token']
        user = await self.fetch_user(request)
        session['user_id'] = int(user['id'])

    async def ensure_logged_in(self, request: web.Request,
                               return_to: Optional[str]) -> None:
        """Ensure that the user is logged in.

        This refreshes tokens if possible and necessary,
        or redirects to the auth endpoint if needed.
        """
        session = await get_session(request)

        # redirect to login if never logged in
        if 'refresh_token' not in session:
            if return_to is None:
                logger.getChild('ensure_logged_in').debug(
                    'No refresh token, refusing to redirect')
                raise web.HTTPUnauthorized
            session['return_to'] = return_to
            location = '/api/oauth2/auth'
            logger.getChild('ensure_logged_in').debug(
                'No refresh token; set return_to = %r and redirecting to %s',
                return_to, location)
            raise web.HTTPTemporaryRedirect(location)

        # refresh token if expired
        if session['expiry'] < time.time():
            logger.getChild('ensure_logged_in').debug(
                'Token expired %.3f seconds ago, refreshing',
                time.time() - session['expiry'])
            async with self.session.post(DISCORD_TOKEN, data={
                'client_id': config.client_id,
                'client_secret': config.client_secret,
                'grant_type': 'refresh_token',
                'refresh_token': session['refresh_token'],
            }) as resp:
                resp.raise_for_status()
                data: TokenResponse = await resp.json()
            await self.set_oauth2(request, data)

    async def ensure_guild_admin(self, request: web.Request) -> discord.Guild:
        """Ensure that the user is an admin in the specified guild.
        Returns the guild if so; raises an HTTP exception if not.
        """
        session = await get_session(request)
        guild = await self.fetch_guild(request)
        if (member := guild.get_member(session['user_id'])) is None \
                or not member.guild_permissions.administrator:
            # not in guild or not admin of guild
            raise web.HTTPForbidden
        return guild

    ### i18n helpers ###

    async def mkmsg(self, request: web.Request, key: str, **kwparams) -> str:
        """Make an i18n message with request context."""
        msg = await self.msgmaker(request)
        return msg(key, **kwparams)

    async def msgmaker(self, request: web.Request,
                       prefix: str = '') -> Callable[..., str]:
        """Returns ``mkmsg`` with the context pre-filled."""
        session = await get_session(request)
        user_object = discord.Object(session['user_id'])
        return lambda key, **kwparams: mkmsg(
            user_object, prefix + key, **kwparams)

    ### View routes ###

    @template('index.jinja2')
    async def index(self, request: web.Request):
        """The homepage."""
        await self.ensure_logged_in(request, '/')

        _ = await self.msgmaker(request, 'server/index/')
        username = (await self.get_user(request))['username']
        logger.getChild('index').debug('Logged in username is %r', username)
        return {
            'hello': _('hello', username=username),
            'settings': _('settings'),
            'servers': _('servers'),
        }

    @template('settings.jinja2')
    async def get_settings(self, request: web.Request):
        """The personal settings page."""
        await self.ensure_logged_in(request, '/settings')

        session = await get_session(request)
        _ = await self.msgmaker(request, 'server/settings/')
        langs = {
            code: str(Msg('@name', lang=code))
            for code in sorted(SUPPORTED_LANGS) if code != 'qqq'
        }
        selected_lang = Msg.user_langs.get(session['user_id'], '')
        logger.getChild('get_settings').debug(
            'Loaded %s user lang: %r',
            session['user_id'], selected_lang)
        return {
            'title': _('title'),
            'language': _('language'),
            'langs': {'': _('lang-auto'), **langs},
            'lang': selected_lang,
            'save': _('save'),
            'back': _('back'),
        }

    async def post_settings(self, request: web.Request):
        """Save your settings."""
        await self.ensure_logged_in(request, None)

        # request data validation
        data = await request.post()
        if not data:
            raise web.HTTPBadRequest(text='Invalid POST body')
        if 'lang' not in data:
            raise web.HTTPBadRequest(text='Missing language setting')
        lang = data.get('lang', '')
        if not isinstance(lang, str):
            raise web.HTTPBadRequest(text='Invalid language setting')
        if lang and lang not in SUPPORTED_LANGS:
            raise web.HTTPBadRequest(text='Unsupported language')
        lang = lang or None # cast '' to None

        # save settings
        session = await get_session(request)
        user_id = session['user_id']
        logger.getChild('post_settings').debug(
            'Setting %s user lang to %r', user_id, lang)
        Msg.user_langs[user_id] = lang
        await db.set_user_lang(user_id, lang)

        # show settings
        return await self.get_settings(request)

    @template('servers.jinja2')
    async def servers(self, request: web.Request):
        """List managed guilds."""
        await self.ensure_logged_in(request, '/servers')

        _ = await self.msgmaker(request, 'server/servers/')
        servers = {
            int(guild['id']): (
                guild['icon'], guild['name'],
                acronym(guild['name'])
            )
            for guild in await self.fetch_guilds(request)
            if discord.Permissions(
                int(guild['permissions'])
            ).administrator
        }
        logger.getChild('servers').debug(
            'Fetched %s guilds', len(servers))
        return {
            'title': _('title'),
            'desc': _('desc'),
            'back': await self.mkmsg(request, 'server/settings/back'),
            'servers': servers,
        }

    @template('server.jinja2')
    async def get_server(self, request: web.Request):
        """The server settings page."""
        await self.ensure_logged_in(request, request.path)

        guild = await self.ensure_guild_admin(request)

        _ = await self.msgmaker(request, 'server/server/')
        s_maker = await self.msgmaker(request, 'server/settings/')

        channels = [(cat, [
            {
                'id': channel.id,
                'name': channel.name,
                'lang': Msg.channel_langs.get(channel.id, ''),
                'voice': hasattr(channel, 'connect'),
            }
            for channel in channels
            if isinstance(channel, discord.abc.Messageable)
        ]) for cat, channels in guild.by_category() if channels]

        langs = {
            code: str(Msg('@name', lang=code))
            for code in sorted(SUPPORTED_LANGS) if code != 'qqq'
        }

        censor = await db.guild_words_censor(guild.id)

        return {
            'title': _('title', guild_name=guild.name),
            'save': s_maker('save'),
            'back': s_maker('back'),
            'channel_th': _('channel-th'),
            'lang_th': _('lang-th'),
            'censor_th': _('censor-th'),
            'channels': channels,
            'langs': {'': s_maker('lang-auto') , **langs},
            'censor': censor,
        }

    async def patch_server(self, request: web.Request):
        """Save server settings."""
        await self.ensure_logged_in(request, None)
        guild = await self.ensure_guild_admin(request)

        _ = await self.msgmaker(request, 'server/server/')
        err = await self.msgmaker(request, 'server/server/error/')

        log = logger.getChild('patch_server')
        results: list[str] = []
        tasks: list[asyncio.Task] = []

        data: GuildSettings = await request.json()
        if not isinstance(data, dict) or not data:
            raise web.HTTPBadRequest(text='Invalid POST body')

        # set censor
        if 'words_censor' in data:
            censor = data['words_censor']
            if not isinstance(censor, str):
                raise web.HTTPBadRequest(text=err('censor-data'))
            log.debug('Setting %s (%s) guild words censor to %r',
                      guild.name, guild.id, censor)
            tasks.append(asyncio.create_task(
                db.set_guild_words_censor(guild.id, censor)))
            results.append(_('censor-set'))

        # set channel data
        if 'channels' in data:
            if not isinstance(data['channels'], dict):
                raise web.HTTPBadRequest(text=err('channel-data'))
            for channel_id, channel_data in data['channels'].items():
                try:
                    channel_id = int(channel_id)
                except ValueError:
                    log.error('Bad channel ID: %r', channel_id)
                    raise web.HTTPBadRequest(text=err('channel-data'))
                channel = guild.get_channel(channel_id)
                if channel is None:
                    log.warning('Channel cache miss: %s', channel_id)
                    try:
                        channel = await guild.fetch_channel(channel_id)
                    except discord.HTTPException:
                        log.exception('No such channel: %s', channel_id)
                        raise web.HTTPNotFound(text=err('channel-missing'))
                if not isinstance(channel, discord.abc.Messageable):
                    # NOTE: remove this if we ever do something
                    # with non-messageable channels
                    log.error('#%s (%s) is non-messageable',
                              channel.name, channel.id)
                    # pretend missing to client
                    raise web.HTTPForbidden(text=err('channel-missing'))
                if not isinstance(channel_data, dict):
                    log.error('Invalid channel data for #%s (%s)',
                              channel.name, channel.id)
                    raise web.HTTPBadRequest(text=err('channel-data'))

                # actual data time! first up - channel language
                if 'lang' in channel_data:
                    lang = channel_data['lang']
                    if not isinstance(lang, str):
                        log.error('Invalid language for #%s (%s): %r',
                                  channel.name, channel.id, lang)
                        raise web.HTTPBadRequest(text=err('channel-lang'))
                    if lang and lang not in SUPPORTED_LANGS:
                        log.error('Unsupported language for #%s (%s): %r',
                                  channel.name, channel.id, lang)
                        raise web.HTTPBadRequest(text=err('channel-lang'))

                    lang = lang or None # cast '' to None
                    log.debug('Setting #%s (%s) channel lang to %r',
                              channel.name, channel.id, lang)
                    Msg.channel_langs[channel.id] = lang
                    tasks.append(asyncio.create_task(
                        db.set_channel_lang(channel.id, lang)))
                    results.append(_('channel-lang-set', channel=channel.name,
                                     language=repr(lang)))

        await asyncio.gather(*tasks)
        if not results:
            raise web.HTTPOk(text=_('did-nothing'))
        raise web.HTTPOk(text='\n'.join(results))
