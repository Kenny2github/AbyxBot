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
    def ended(self) -> bool:
        """Has the game ended?"""
        raise NotImplementedError

    def won(self, *args, **kwargs) -> bool:
        """Assuming the game has ended, did the player win?

        This may take whatever arguments are useful.
        Usually for a singleplayer game this is none,
        or for a multiplayer game it is the player to check for.
        """
        raise NotImplementedError
