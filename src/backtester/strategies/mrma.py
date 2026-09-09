"""Moving-average mean-reversion strategy."""
from collections import deque
from typing import Sequence, Callable

from backtester.domain.market import Candle
from backtester.strategies.base import SingleAssetStrategy
from backtester.domain.trading import Signal
from backtester.strategies.calculators import MovingAverageCalculator, SimpleMovingAverageCalculator, \
    ExponentialMovingAverageCalculator


class MeanReversionStrategy(SingleAssetStrategy):
    def __init__(self,
                 window: int,
                 threshold: float,
                 factory: Callable[[int], MovingAverageCalculator]):
        if not window > 0:
            raise ValueError("window must be positive integer")

        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")

        self._calculator = factory(window)
        self._threshold: float = threshold

    def on_candle(self, candle: Candle) -> Signal:
        price = candle.close
        avg = self._calculator.next_value(price)
        if avg is None:
            return Signal.HOLD

        if price < avg * self._threshold:
            return Signal.BUY
        elif price >= avg:
            return Signal.SELL
        else:
            return Signal.HOLD

    def reset(self):
        self._calculator.reset()

class SimpleMeanReversionStrategy(MeanReversionStrategy):
    def __init__(self, window: int, threshold: float):
        super().__init__(window, threshold, SimpleMovingAverageCalculator)

class ExponentialMeanReversionStrategy(MeanReversionStrategy):
    def __init__(self, window: int, threshold: float):
        super().__init__(window, threshold, ExponentialMovingAverageCalculator.standard)
