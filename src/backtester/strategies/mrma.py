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


class _MeanReversionStrategy(SingleAssetStrategy):
    """Buy below a fraction of the rolling mean and sell at or above it."""

    def __init__(self, window: int, threshold: float):
        if not window > 0:
            raise ValueError("window must be positive integer")

        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")

        self._window_len: int = window
        self._threshold: float = threshold
        self._sum: float = 0
        self._window = deque(maxlen=self._window_len)

    def on_candle(self, candle: Candle) -> Signal:
        price = candle.close
        self._update_state(candle.close)
        if len(self._window) < self._window_len:
            return Signal.HOLD

        average = self._sum / self._window_len

        if price < average * self._threshold:
            return Signal.BUY
        elif price >= average:
            return Signal.SELL
        else:
            return Signal.HOLD

    def reset(self):
        self._sum: float = 0
        self._window.clear()

    def _update_state(self, price: float):
        if len(self._window) >= self._window_len:
            self._sum -= self._window.popleft()

        self._sum += price
        self._window.append(price)

    # def generate_signal(
    #     self, candles: Sequence[Candle]) -> Signal:
    #     """Generate a signal from the latest close and rolling close mean."""
    #
    #     if len(candles) < self._window_len:
    #         return Signal.HOLD
    #
    #     average = sum(candle.close for candle in candles[-self._window_len:]) / self._window_len
    #     price = candles[-1].close
    #
    #     if price < average * self._threshold:
    #         return Signal.BUY
    #     elif price >= average:
    #         return Signal.SELL
    #     else:
    #         return Signal.HOLD
    #