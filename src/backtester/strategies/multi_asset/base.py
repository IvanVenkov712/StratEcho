from abc import ABC, abstractmethod

from backtester.domain.market import MarketFrame
from backtester.domain.trading import MultiAssetSignal


class MultiAssetStrategy(ABC):

    @abstractmethod
    def on_frame(self, frame: MarketFrame) -> MultiAssetSignal:
        pass

    @abstractmethod
    def reset(self) -> None:
        pass
