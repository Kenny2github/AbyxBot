from typing import Optional
from abc import ABCMeta, abstractmethod

class GameEngine(metaclass=ABCMeta):

    @abstractmethod
    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError

    @abstractmethod
    def update(self, *args, **kwargs):
        """Update the game state.

        This may take whatever arguments and return whatever value is useful.
        """
        raise NotImplementedError

    @abstractmethod
    def won(self, *args, **kwargs) -> Optional[bool]:
        """Has the game ended by winning?

        This may take whatever arguments are useful.
        Usually for a singleplayer game this is none,
        or for a multiplayer game it is the player to check for.

        Returns:
        * ``True`` for yes
        * ``None`` if the game has ended, but not by winning
        * ``False`` if the game has not yet ended
        """
        raise NotImplementedError
