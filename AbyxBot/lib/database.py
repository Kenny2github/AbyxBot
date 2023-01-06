# stdlib
import os
from logging import getLogger
from typing import Any, Optional, Union, overload
import asyncio
from typing_extensions import LiteralString

# 3rd-party
import aiofiles
import aiosqlite

__all__ = [
    'db',
    'Database',
    'id_to_game',
    'game_to_id',
]

logger = getLogger(__name__)

id_to_game: dict[int, str] = {}
game_to_id: dict[str, int] = {}

class Database:
    """Represents the database connection."""

    _inst = None
    DB_FILE = 'abyxbot.db'
    DB_VERSION = 1 # latest version
    SQL_DIR = os.path.join('AbyxBot', 'sql')

    conn: Optional[aiosqlite.Connection] = None
    cur: aiosqlite.Cursor
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
            current_version = (await self.cur.fetchone() or [-1])[0]
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
        if self.conn is None:
            raise RuntimeError('Cannot stop an unconnected database')
        await self.conn.commit()
        await self.conn.close()
        self.conn = None
        del self.cur

    ## helper methods

    async def _obj_settings(
        self, obj_type: LiteralString, setting: LiteralString = 'lang',
        table: Optional[LiteralString] = None
    ) -> dict[int, Any]:
        """Internal use generic [obj]_id->[setting] fetcher."""
        settings: dict[int, Any] = {}
        query = f'SELECT {obj_type}_id, {setting} FROM {table or obj_type+"s"}'
        async with self.lock:
            await self.cur.execute(query)
            async for row in self.cur:
                settings[row[f'{obj_type}_id']] = row[setting]
        return settings

    async def _obj_settings_multiple(
        self, obj_type: LiteralString, setting: LiteralString,
        table: Optional[LiteralString] = None,
        # dict default is dangerous, but only if modified
        where: dict[LiteralString, Any] = {},
    ) -> dict[int, list[Any]]:
        """Internal use generic [obj]_id->[setting, ...] fetcher."""
        settings: dict[int, list[Any]] = {}
        query = f'SELECT {obj_type}_id, {setting} FROM {table or obj_type+"s"}'
        if where:
            query += ' WHERE '
            query += ' AND '.join(f'{key}=:{key}' for key in where)
        async with self.lock:
            if where:
                await self.cur.execute(query, where)
            else:
                await self.cur.execute(query)
            async for row in self.cur:
                settings.setdefault(
                    row[f'{obj_type}_id'], []).append(row[setting])
        return settings

    async def _obj_get(
        self, obj_type: LiteralString, obj_id: int,
        setting: LiteralString, table: Optional[LiteralString] = None
    ) -> Any:
        """Internal use generic [obj]_id->[setting] fetcher."""
        query = f'SELECT {obj_type}_id, {setting} FROM {table or obj_type+"s"}'
        query += f' WHERE {obj_type}_id=?'
        async with self.lock:
            await self.cur.execute(query, (obj_id,))
            row = await self.cur.fetchone()
            if row is None:
                return None
            return row[setting]

    async def _obj_get_multiple(
        self, obj_type: LiteralString, obj_id: int,
        setting: LiteralString, table: Optional[LiteralString] = None
    ) -> list[Any]:
        """Internal use generic [obj]_id->[setting, ...] fetcher."""
        query = f'SELECT {obj_type}_id, {setting} FROM {table or obj_type+"s"}'
        query += f' WHERE {obj_type}_id=?'
        async with self.lock:
            await self.cur.execute(query, (obj_id,))
            return [row[setting] async for row in self.cur]

    async def _obj_set(
        self, obj_type: LiteralString, obj_id: int, setting: LiteralString,
        value: Any, table: Optional[LiteralString] = None
    ) -> None:
        """Internal use generic upsert [obj][obj_id].[setting] = [value]."""
        query = \
            f'INSERT INTO {table or obj_type+"s"} ({obj_type}_id, ' \
            f'{setting}) VALUES (?, ?) ON CONFLICT({obj_type}_id) DO ' \
            f'UPDATE SET {setting}=excluded.{setting}'
        await self.cur.execute(query, (obj_id, value))

    async def _obj_set_multiple(
        self, obj_type: LiteralString, obj_id: int, setting: LiteralString,
        value: Any, table: Optional[LiteralString] = None,
        on_conflict: LiteralString = 'DO NOTHING',
    ) -> None:
        """Internal use generic set(obj).add(([obj_id], [value]))."""
        query = \
            f'INSERT INTO {table or obj_type+"s"} ({obj_type}_id, ' \
            f'{setting}) VALUES (?, ?) ON CONFLICT {on_conflict}'
        await self.cur.execute(query, (obj_id, value))

    async def _obj_del_multiple(
        self, obj_type: LiteralString, obj_id: int, setting: LiteralString,
        value: Any, table: Optional[LiteralString] = None,
    ) -> None:
        """Internal use generic set(obj).discard(([obj_id], [value]))."""
        query = \
            f'DELETE FROM {table or obj_type+"s"} ' \
            f'WHERE {obj_type}_id=? AND {setting}=?'
        await self.cur.execute(query, (obj_id, value))

    async def _objs_by_setting(
        self, obj_type: LiteralString, setting: LiteralString,
        value: Any, table: Optional[LiteralString] = None,
    ) -> list[int]:
        """Internal use generic [obj] where [setting]=value."""
        query = f'SELECT {obj_type}_id FROM {table or obj_type+"s"} '\
            f'WHERE {setting}=?'
        async with self.lock:
            await self.cur.execute(query, (value,))
            return [row[f'{obj_type}_id'] async for row in self.cur]

    async def _touch(self, obj_type: LiteralString, obj_id: int) -> None:
        """Internal use generic create row if not exists."""
        query = f'INSERT INTO {obj_type}s ({obj_type}_id) VALUES (?)' \
            f'ON CONFLICT({obj_type}_id) DO NOTHING'
        await self.cur.execute(query, (obj_id,))

    ## guild-related methods

    async def touch_guild(self, guild_id: int) -> None:
        """Create a guild database row if it does not exist."""
        await self._touch('guild', guild_id)

    async def guild_words_censor(self, guild_id: int) -> str:
        """Fetch the guild /words censor."""
        return (await self._obj_get('guild', guild_id, 'words_censor')) or ''

    async def set_guild_words_censor(self, guild_id: int, censor: str) -> None:
        """Change a guild's /words censor."""
        await self._obj_set('guild', guild_id, 'words_censor', censor)

    ## user-related methods

    async def touch_user(self, user_id: int) -> None:
        """Create a user database row if it does not exist."""
        await self._touch('user', user_id)

    async def user_langs(self) -> dict[int, Optional[str]]:
        """Fetch user language settings."""
        return await self._obj_settings('user')

    async def set_user_lang(self, user_id: int, lang: Optional[str]) -> None:
        """Change a user's language setting."""
        await self._obj_set('user', user_id, 'lang', lang)

    async def game_user_pings(self, game: str) -> list[int]:
        """Get users to ping for the game."""
        return await self._objs_by_setting(
            'user', 'game', game_to_id[game], 'user_game_pings')

    async def user_game_pings(self, user_id: int) -> list[str]:
        """Get a user's game ping settings."""
        data = await self._obj_get_multiple(
            'user', user_id, 'game', 'user_game_pings')
        return [id_to_game[game] for game in data]

    async def set_user_game_pings(self, user_id: int, games: list[str]) -> None:
        """Set a user's game ping settings."""
        await self.touch_user(user_id) # to obey foreign keys
        remove_the_old = 'DELETE FROM user_game_pings '\
            'WHERE user_id=? AND game NOT IN (' \
            + ', '.join('?' * len(games)) + ')'
        welcome_the_new = 'INSERT INTO user_game_pings (user_id, game) ' \
            'VALUES (?, ?) ON CONFLICT DO NOTHING'
        game_ids = [game_to_id[game] for game in games]
        async with self.lock:
            await self.cur.execute(remove_the_old, (user_id, *game_ids))
            await self.cur.executemany(
                welcome_the_new, [(user_id, game) for game in game_ids])

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
        await self._obj_set('channel', channel_id, 'lang', lang)

    async def game_channel_pings(self, game: str) -> list[int]:
        """Get channels to ping for the game."""
        return await self._objs_by_setting(
            'channel', 'game', game_to_id[game], 'channel_game_pings')

    @overload
    async def channel_game_pings(self, *, guild_id: Optional[int]
                                 ) -> dict[int, list[str]]: ...
    @overload
    async def channel_game_pings(self, channel_id: int) -> list[str]: ...

    async def channel_game_pings(
        self, channel_id: Optional[int] = None,
        *, guild_id: Optional[int] = None,
    ) -> Union[dict[int, list[str]], list[str]]:
        """Get the games to ping the channel for."""
        if channel_id is None:
            data = await self._obj_settings_multiple(
                'channel', 'game', 'channel_game_pings',
                {} if guild_id is None else {'guild_id': guild_id})
            return {channel_id: [id_to_game[game] for game in games]
                    for channel_id, games in data.items()}
        data = await self._obj_get_multiple(
            'channel', channel_id, 'game', 'channel_game_pings')
        return [id_to_game[game] for game in data]

    async def add_channel_game_ping(self, guild_id: int,
                                    channel_id: int, game: str) -> None:
        """Enable pings for this game in this channel."""
        await self.touch_guild(guild_id)
        await self.touch_channel(channel_id) # to obey foreign keys
        query = \
            'INSERT INTO channel_game_pings (channel_id, game, guild_id) ' \
            'VALUES (?, ?, ?) ON CONFLICT DO NOTHING'
        await self.cur.execute(query, (channel_id, game_to_id[game], guild_id))

    async def del_channel_game_ping(self, channel_id: int, game: str) -> None:
        """Disable pings for this game in this channel."""
        await self._obj_del_multiple('channel', channel_id, 'game',
                                     game_to_id[game], 'channel_game_pings')

    ## methods for 2048

    async def get_2048_highscore(self, user_id: int) -> int:
        """Get the highscore for a user in 2048."""
        await self.touch_user(user_id)
        return (await self._obj_get(
            'user', user_id, 'score', 'pow211_highscores'
        )) or 0

    async def set_2048_highscore(self, user_id: int, score: int) -> None:
        """Set the highscore for a user in 2048."""
        await self._obj_set('user', user_id, 'score', score,
                            'pow211_highscores')

db: Database = Database()
