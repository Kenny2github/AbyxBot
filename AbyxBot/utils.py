# stdlib
import re
import asyncio
import os
from contextlib import contextmanager
from typing import Generic, Iterator, Optional, TypeVar
from functools import partial

# 3rd-party
import discord

T = TypeVar('T')
EMOJI_RE = re.compile(r'<(a?):([^:]+):([^>]+)>')

class AttrDict(dict[str, T]):
    """Access data by key or attribute."""
    def __init__(self, attrs: dict[str, T]):
        self.update(attrs)
    def __getattr__(self, name: str) -> T:
        return self[name]
    def __setattr__(self, name: str, value: T) -> None:
        self[name] = value

def recurse_mtimes(dir: str, *path: str,
                   current: Optional[dict[str, float]] = None
                   ) -> dict[str, float]:
    """Recursively get the mtimes of all files of interest."""
    if current is None:
        current = {}
    for item in os.listdir(os.path.join(*path, dir)):
        fullitem = os.path.join(*path, dir, item)
        if os.path.isdir(fullitem):
            recurse_mtimes(item, *path, dir, current=current)
        elif item.endswith(('.py', '.sql', '.json')):
            current[fullitem] = os.path.getmtime(fullitem)
    return current

def similarity(a: str, b: str) -> float:
    """Calculate the Levenshtein ratio of similarity between a and b.

    Adapted from:
    https://www.datacamp.com/community/tutorials/fuzzy-string-python
    """
    rows = len(a) + 1
    cols = len(b) + 1
    distance = [[0] * cols for _ in range(rows)]

    for i in range(1, rows):
        for j in range(1, cols):
            distance[i][0] = i
            distance[0][j] = j

    row = col = 1
    for col in range(1, cols):
        for row in range(1, rows):
            if a[row-1] == b[col-1]:
                cost = 0
            elif a[row-1].casefold() == b[col-1].casefold():
                cost = 1  # don't penalize capitalization changes as much
            else:
                cost = 2
            distance[row][col] = min(
                distance[row-1][col] + 1,
                distance[row][col-1] + 1,
                distance[row-1][col-1] + cost
            )

    return 1 - distance[row][col] / (len(a) + len(b))

async def asyncify(func, *args, **kwargs):
    """Run a synchronous function in an executor."""
    return await asyncio.get_event_loop().run_in_executor(
        None, partial(func, *args, **kwargs))

def str_to_emoji(s: str) -> discord.PartialEmoji:
    match = EMOJI_RE.match(s)
    if not match:
        raise ValueError(f'Invalid emoji string {s}')
    return discord.PartialEmoji(name=match.group(2),
                                animated=bool(match.group(1)),
                                id=int(match.group(3)))

KT = TypeVar('KT')
VT = TypeVar('VT')
def dict_pop_n(n: int, d: dict[KT, VT]) -> dict[KT, VT]:
    """Pop at most ``n`` items from the dict and return them as a new dict.

    If there are fewer than ``n`` items in the dict, it will be cleared
    and a copy of the original will be returned.

    Note that this pops in FIFO order, unlike ``dict.popitem()``.
    """
    result: dict[KT, VT] = {}
    keys_to_pop = list(d.keys())[:n]
    for key in keys_to_pop:
        result[key] = d.pop(key)
    return result

class BroadcastQueue(Generic[T]):
    """A queue that broadcasts to all waiting coroutines."""

    queues: set[asyncio.Queue[T]]

    def __init__(self) -> None:
        self.queues = set()

    def register(self) -> asyncio.Queue[T]:
        """Register this coroutine to the broadcast.

        Consume this queue like normal, but do not put to it.
        """
        q = asyncio.Queue()
        self.queues.add(q)
        return q

    def deregister(self, queue: asyncio.Queue[T]) -> None:
        """Deregister this queue, previously returned by register()."""
        self.queues.remove(queue)

    @contextmanager
    def consume(self) -> Iterator[asyncio.Queue[T]]:
        """Context manager that yields a registered queue
        and deregisters it on exit.
        """
        q = self.register()
        try:
            yield q
        except Exception:
            import traceback
            traceback.print_exc()
            raise
        finally:
            self.deregister(q)

    def put_nowait(self, item: T) -> None:
        """Broadcast an item to all registered queues, without waiting."""
        for q in self.queues:
            q.put_nowait(item)

    async def put(self, item: T) -> None:
        """Broadcast an item to all registered queues."""
        await asyncio.gather(*(q.put(item) for q in self.queues))

    async def join(self) -> None:
        """Join every registered queue.

        Use with care - may hang if a consuming coroutine forgets to
        deregister itself. Use consume() to avoid that.
        """
        await asyncio.gather(*(q.join() for q in self.queues))
