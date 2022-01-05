# stdlib
import asyncio
import os
from typing import Optional

# 3rd-party
import aiofiles
import aiosqlite

# 1st-party
from .logger import get_logger

__all__ = [
    'db',
    'Database'
]

logger = get_logger('db')

class Database:
    """Represents the database connection."""

    _inst = None
    DB_FILE = 'abyxbot.db'
    DB_VERSION = 1 # latest version
    SQL_DIR = os.path.join('AbyxBot', 'sql')

    conn: Optional[aiosqlite.Connection] = None
    cur: Optional[aiosqlite.Cursor] = None
    lock = asyncio.Lock()

    def __new__(cls):
        """The database connection is a singleton."""
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    async def init(self):
        """Open a connection to the database and create schema if necessary.
        The Database is usable from this point forward.
        """
        self.conn = await aiosqlite.connect(self.DB_FILE)
        self.conn.row_factory = aiosqlite.Row
        self.cur = await self.conn.cursor()
        async with self.lock:
            await self.cur.execute('PRAGMA user_version')
            current_version = (await self.cur.fetchone())[0]
        if current_version == self.DB_VERSION:
            logger.info('Latest database version (%s) matches current (%s)',
                        current_version, self.DB_VERSION)
            return
        if current_version > self.DB_VERSION:
            raise RuntimeError(
                f'Outdated DB version: ours is {self.DB_VERSION}, '
                f'saved is {current_version}')
        logger.info('Database is outdated, upgrading from %s to %s',
                    current_version, self.DB_VERSION)
        for ver in range(current_version + 1, self.DB_VERSION + 1):
            sqlfile = os.path.join(self.SQL_DIR, f'v{ver}.sql')
            if not os.path.isfile(sqlfile):
                logger.info('  No script for v%s, skipping', ver)
                continue
            async with aiofiles.open(sqlfile) as f:
                logger.info('  v%s -> v%s', ver - 1, ver)
                try:
                    await self.cur.executescript(await f.read())
                except aiosqlite.OperationalError:
                    logger.exception('    Upgrading failed:')
        # can't use quoting with PRAGMA statements, so I have to do
        # something very illegal here and directly substitute a value
        query = f'PRAGMA user_version = {self.DB_VERSION}'
        logger.info(query)
        await self.cur.execute(query)

    async def stop(self):
        """Commit and close the connection to the database.
        The Database is unusable from this point forward.
        """
        await self.conn.commit()
        await self.conn.close()
        self.conn = self.cur = None

    ## helper methods

    async def _obj_settings(
        self, obj_type: str, setting: str = 'lang', table: str = None
    ) -> dict[int, Optional[str]]:
        """Internal use generic [obj]_id->[setting] fetcher."""
        settings: dict[int, Optional[str]] = {}
        query = f'SELECT {obj_type}_id, {setting} FROM {table or obj_type+"s"}'
        async with self.lock:
            await self.cur.execute(query)
            async for row in self.cur:
                settings[row[f'{obj_type}_id']] = row[setting]
        return settings

    async def _obj_set(
        self, obj_type: str, obj_id: int, value: Optional[str],
        setting: str = 'lang', table: str = None
    ) -> None:
        """Internal use generic upsert [obj][obj_id].[setting] = [value]."""
        query = \
            f'INSERT INTO {table or obj_type+"s"} ({obj_type}_id, ' \
            f'{setting}) VALUES (?, ?) ON CONFLICT({obj_type}_id) DO ' \
            f'UPDATE SET {setting}=excluded.{setting}'
        await self.cur.execute(query, (obj_id, value))

    async def _touch(self, obj_type: str, obj_id: int) -> None:
        """Internal use generic create row if not exists."""
        query = f'INSERT INTO {obj_type}s ({obj_type}_id) VALUES (?)' \
            f'ON CONFLICT({obj_type}_id) DO NOTHING'
        await self.cur.execute(query, (obj_id,))

    ## guild-related methods

    async def touch_guild(self, guild_id: int) -> None:
        """Create a guild database row if it does not exist."""
        await self._touch('guild', guild_id)

    ## user-related methods

    async def touch_user(self, user_id: int) -> None:
        """Create a user database row if it does not exist."""
        await self._touch('user', user_id)

    async def user_langs(self) -> dict[int, Optional[str]]:
        """Fetch user language settings."""
        return await self._obj_settings('user')

    async def set_user_lang(self, user_id: int, lang: Optional[str]) -> None:
        """Change a user's language setting."""
        await self._obj_set('user', user_id, lang)

    ## channel-related methods

    async def touch_channel(self, channel_id: int) -> None:
        """Create a channel database row if it does not exist."""
        await self._touch('channel', channel_id)

    async def channel_langs(self) -> dict[int, Optional[str]]:
        """Fetch channel language settings."""
        return await self._obj_settings('channel')

    async def set_channel_lang(
        self, channel_id: int, lang: Optional[str]
    ) -> None:
        """Change a channel's language setting."""
        await self._obj_set('channel', channel_id, lang)

db: Database = Database()
