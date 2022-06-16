# stdlib
from typing import Protocol, Union, runtime_checkable, AsyncIterator

# 3rd-party
import discord

@runtime_checkable
class Mentionable(discord.abc.Snowflake, Protocol):

    @property
    def mention(self) -> str:
        raise NotImplementedError

ChannelLike = Union[discord.abc.GuildChannel, discord.Thread]

@runtime_checkable
class NamespaceChannel(discord.abc.Snowflake, Protocol):
    def resolve(self) -> ChannelLike:
        raise NotImplementedError

@runtime_checkable
class HistoriedChannel(discord.abc.Snowflake, Protocol):
    async def purge(self, **kwargs) -> list[discord.Message]:
        raise NotImplementedError
    def history(self, **kwargs) -> AsyncIterator[discord.Message]:
        raise NotImplementedError
    async def fetch_message(self, message_id: int) -> discord.Message:
        raise NotImplementedError
