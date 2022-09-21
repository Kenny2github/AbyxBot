from contextlib import asynccontextmanager
import os
from secrets import token_urlsafe
from logging import getLogger
from typing import AsyncIterator, Optional
from urllib.parse import urlencode, urlparse
from aiohttp import ClientSession, web
import aiohttp_cors
from ..config import config
from ..database import db

DISCORD_API = 'https://discord.com/api/v10'
DISCORD_OAUTH2 = 'https://discord.com/oauth2/authorize'
CLIENT_ID: int = config.client_id
CLIENT_SECRET: str = config.client_secret
WEB_ROOT: str = config.web_root
REDIRECT_URI: str = WEB_ROOT + '/api/oauth2_callback'
FILE_ROOT: Optional[str] = config.file_root
SCOPES = 'identify guilds'
TOKEN_TYPE = 'Bearer'

logger = getLogger(__name__)

class Handler:
    """Request handler class for the server."""

    def __init__(self) -> None:
        self.app = web.Application()
        cors = aiohttp_cors.setup(self.app, defaults={
            "https://bot.abyx.dev": aiohttp_cors.ResourceOptions(
                allow_methods='*',
                allow_headers='*'),
            "http://localhost:3000": aiohttp_cors.ResourceOptions(
                allow_methods='*',
                allow_headers='*'),
        })

        for route in self.app.add_routes([
            web.get('/api/oauth2_url', self.oauth2_url),
            web.post('/api/oauth2_token', self.oauth2_token),
            web.post('/api/oauth2_refresh', self.oauth2_refresh),
        ]):
            cors.add(route)
        if FILE_ROOT is not None:
            self.app.add_routes([web.static('/', FILE_ROOT)])
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

    async def oauth2_url(self, request: web.Request) -> web.Response:
        state = token_urlsafe()
        return web.json_response(data={'url': DISCORD_OAUTH2 + '?' + urlencode({
            'client_id': CLIENT_ID,
            'scope': 'identify guilds',
            'response_type': 'code',
            'redirect_uri': REDIRECT_URI,
            'state': state,
            'prompt': 'none',
        }), 'state': state})

    async def oauth2_token(self, request: web.Request) -> web.Response:
        # we are assuming that the client has validated the state
        code: str = request.query['code']
        async with self.session.post(DISCORD_API + '/oauth2/token', data={
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI,
        }) as response:
            if not response.ok:
                return web.Response(
                    status=response.status, text=await response.text(),
                    content_type=response.content_type or None
                )
            data = await response.json()
        return web.json_response(data)
