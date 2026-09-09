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
        super().__init__(
            lambda size: SimpleMovingAverageCalculator(size),
            short_window_size,
            long_window_size
        )

class ExponentialMovingAverageCrossStrategy(MovingAverageCrossStrategy):
    def __init__(self, short_window_size: int = 20, long_window_size: int = 50):
        super().__init__(
            ExponentialMovingAverageCalculator.standard,
            short_window_size,
            long_window_size
        )
