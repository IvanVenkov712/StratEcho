"""Simple moving-average crossover strategy."""
from collections import deque
from typing import Callable

from backtester.domain.market import Candle
from backtester.strategies.base import SingleAssetStrategy
from backtester.domain.trading import Signal
from backtester.strategies.calculators import MovingAverageCalculator, SimpleMovingAverageCalculator, \
    ExponentialMovingAverageCalculator


class MovingAverageCrossStrategy(SingleAssetStrategy):
    def __init__(self,
                 factory: Callable[[int], MovingAverageCalculator],
                 short_window_size: int = 20,
                 long_window_size: int = 50):
        if short_window_size <= 0 or long_window_size <= 0:
            raise ValueError("Window sizes must be positive")

        if short_window_size >= long_window_size:
            raise ValueError("short_window must be smaller than long_window")

        self._long_calculator: MovingAverageCalculator = factory(long_window_size)
        self._short_calculator: MovingAverageCalculator = factory(short_window_size)
        self._old_long_avg: float| None = None
        self._old_short_avg: float| None = None

    def on_candle(self, candle: Candle) -> Signal:
        long_avg = self._long_calculator.next_value(candle.close)
        short_avg = self._short_calculator.next_value(candle.close)
        if long_avg is None or short_avg is None:
            return Signal.HOLD

        if self._old_long_avg is None or self._old_short_avg is None:
            self._old_long_avg = long_avg
            self._old_short_avg = short_avg
            return Signal.HOLD

        if self._old_short_avg >= self._old_long_avg and short_avg < long_avg:
            signal = Signal.SELL

        elif self._old_short_avg <= self._old_long_avg and short_avg > long_avg:
            signal = Signal.BUY

        else:
            signal = Signal.HOLD

        self._old_long_avg = long_avg
        self._old_short_avg = short_avg
        return signal

    def reset(self):
        self._long_calculator.reset()
        self._short_calculator.reset()
        self._old_long_avg = None
        self._old_short_avg = None

class SimpleMovingAverageCrossStrategy(MovingAverageCrossStrategy):
    def __init__(self, short_window_size: int = 20, long_window_size: int = 50):
        super().__init__(lambda size: SimpleMovingAverageCalculator(size),
                         short_window_size,
                         long_window_size)

class ExponentialMovingAverageCrossStrategy(MovingAverageCrossStrategy):
    def __init__(self, short_window_size: int = 20, long_window_size: int = 50):
        super().__init__(ExponentialMovingAverageCalculator.standard,
                         short_window_size,
                         long_window_size)


class _MovingAverageCrossStrategy(SingleAssetStrategy):
    """Trade when a short close-price average crosses a longer average.

    A cross above produces a buy and a cross below produces a sell. Signals
    remain on hold until both current and previous windows are available.
    """

    def __init__(self, short_window: int, long_window: int):
        if short_window <= 0 or long_window <= 0:
            raise ValueError("Window sizes must be positive")

        if short_window >= long_window:
            raise ValueError("short_window must be smaller than long_window")

        self._short_window_len: int = short_window
        self._long_window_len: int = long_window

        self._long_sum: float = 0
        self._short_sum: float = 0

        self._long_window = deque(maxlen=self._long_window_len)
        self._short_window = deque(maxlen=self._short_window_len)

        self._counter = 0

    def on_candle(self, candle: Candle) -> Signal:
        old_long_avg = self._long_sum / self._long_window_len
        old_short_avg = self._short_sum / self._short_window_len

        self._update_state(candle.close)

        if self._counter < self._long_window_len:
            self._counter += 1
            return Signal.HOLD

        new_long_avg = self._long_sum / self._long_window_len
        new_short_avg = self._short_sum / self._short_window_len

        if old_short_avg >= old_long_avg and new_short_avg < new_long_avg:
            return Signal.SELL

        elif old_short_avg <= old_long_avg and new_short_avg > new_long_avg:
            return Signal.BUY

        else:
            return Signal.HOLD

    def _update_state(self, price: float):
        if len(self._long_window) >= self._long_window_len:
            self._long_sum -= self._long_window.popleft()

        if len(self._short_window) >= self._short_window_len:
            self._short_sum -= self._short_window.popleft()

        self._long_sum += price
        self._short_sum += price
        self._long_window.append(price)
        self._short_window.append(price)

    def reset(self):
        self._long_sum: float = 0
        self._short_sum: float = 0

        self._long_window = deque(maxlen=self._long_window_len)
        self._short_window = deque(maxlen=self._short_window_len)

        self._counter = 0
