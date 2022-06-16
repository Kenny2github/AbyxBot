# stdlib
from typing import Protocol, Union, runtime_checkable

# 3rd-party
import discord

@runtime_checkable
class Mentionable(discord.abc.Snowflake, Protocol):

    @property
    def mention(self) -> str:
        raise NotImplementedError

ChannelLike = Union[discord.abc.GuildChannel, discord.Thread]

@runtime_checkable
class NamespaceChannel(Protocol):
    def resolve(self) -> ChannelLike:
        raise NotImplementedError
