import asyncio
import os
from typing import Optional, TypeVar
from functools import partial

T = TypeVar('T')

class AttrDict:
    """Access data by key or attribute."""
    def __init__(self, attrs: dict[str, T]):
        self.__dict__.update(attrs)
    def __getitem__(self, key: str) -> T:
        return self.__dict__[key]
    def __setitem__(self, key: str, value: T):
        self.__dict__[key] = value
    def __repr__(self) -> str:
        return repr(self.__dict__)
    def __str__(self) -> str:
        return str(self.__dict__)
    def get(self, key: str, default: T = None) -> Optional[T]:
        return self.__dict__.get(key, default)

def recurse_mtimes(dir: str, *path: str,
                   current: dict[str, float] = None) -> dict[str, float]:
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
    return await asyncio.get_event_loop().run_in_executor(
        None, partial(func, *args, **kwargs))