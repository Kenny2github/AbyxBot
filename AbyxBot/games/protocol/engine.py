from abc import ABCMeta, abstractmethod

class GameEngine(metaclass=ABCMeta):

    @abstractmethod
    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError

    @abstractmethod
    def update(self, *args, **kwargs):
        raise NotImplementedError