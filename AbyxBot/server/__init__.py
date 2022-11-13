# stdlib
from contextlib import asynccontextmanager
import time
from secrets import token_bytes, token_hex
from functools import partial
from logging import getLogger
from pathlib import Path
from typing import AsyncIterator, TypedDict, NoReturn, Callable
from urllib.parse import urlencode, urlparse

# 3rd-party
from aiohttp import ClientSession, web
from aiohttp_jinja2 import setup as setup_jinja2, template
import jinja2
from aiohttp_session import setup as setup_session, get_session as _get_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
import discord

# 1st-party
from ..config import config
from ..i18n import mkmsg
from ..database import db

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

async def get_session(request: web.Request) -> SessionData:
    """Passthru for type casting"""
    return await _get_session(request) # type: ignore

class Handler:
    """Request handler class for the server."""

    def __init__(self) -> None:
        self.app = web.Application()

        # set up Jinja2
        setup_jinja2(self.app, loader=jinja2.FileSystemLoader(
            [Path(__file__).parent / 'templates']))

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
            web.get('/', self.index)
        ])

        self.user_cache: dict[int, dict] = {}

        self.session = ClientSession()
        self.runner = web.AppRunner(self.app)

    async def start(self) -> None:
        await self.runner.setup()
        web_root = urlparse(WEB_ROOT)
        site = web.TCPSite(self.runner, web_root.hostname, web_root.port)
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
            'prompt': 'consent', # 'none',
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
        self.user_cache[user['id']] = user
        return user

    async def fetch_guilds(self, request: web.Request) -> list[dict]:
        """Fetch the logged in user's guilds."""
        session = await get_session(request)
        headers = {'Authorization': f"Bearer {session['access_token']}"}
        async with self.session.get(
            DISCORD_API + '/users/@me/guilds',
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    ### session helpers ###

    async def set_oauth2(self, request: web.Request,
                         token: TokenResponse) -> None:
        """Update OAuth2 cookie data."""
        session = await get_session(request)
        session['access_token'] = token['access_token']
        session['expiry'] = time.time() + token['expires_in'] - 1
        session['refresh_token'] = token['refresh_token']
        user = await self.fetch_user(request)
        session['user_id'] = user['id']

    async def ensure_logged_in(self, request: web.Request,
                               return_to: str) -> None:
        """Ensure that the user is logged in.

        This refreshes tokens if possible and necessary,
        or redirects to the auth endpoint if needed.
        """
        session = await get_session(request)

        # redirect to login if never logged in
        if 'refresh_token' not in session:
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

    ### i18n helpers ###

    async def mkmsg(self, request: web.Request, key: str, **kwparams) -> str:
        """Make an i18n message with request context."""
        msg = await self.msgmaker(request)
        return msg(key, **kwparams)

    async def msgmaker(self, request: web.Request) -> Callable[..., str]:
        """Returns ``mkmsg`` with the context pre-filled."""
        session = await get_session(request)
        user_object = discord.Object(session['user_id'])
        return partial(mkmsg, user_object)

    ### View routes ###

    @template('index.jinja2')
    async def index(self, request: web.Request):
        """The homepage."""
        await self.ensure_logged_in(request, '/')

        _ = await self.msgmaker(request)
        username = (await self.get_user(request))['username']
        logger.getChild('index').debug('Logged in username is %r', username)
        return {
            'hello': _('server/index/hello', username=username),
            'settings': _('server/index/settings'),
            'servers': _('server/index/servers'),
        }
