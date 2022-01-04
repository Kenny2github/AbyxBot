import os
from typing import Optional, TypeVar

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
