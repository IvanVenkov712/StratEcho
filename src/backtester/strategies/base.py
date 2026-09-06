"""Strategy interface for chronological signal generation."""

from abc import ABC, abstractmethod
from typing import Sequence

from backtester.domain.market import Candle
from backtester.domain.trading import Signal


class SingleAssetStrategy(ABC):
    """Generate trading signals from market history available so far."""

    @abstractmethod
    def on_candle(self, candle: Candle) -> Signal:
        """Return a signal using only the supplied chronological candles."""
        pass

    @abstractmethod
    def reset(self):
        pass