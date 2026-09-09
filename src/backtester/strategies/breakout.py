"""Donchian-channel breakout strategy."""
from typing import Callable

from backtester.domain.market import Candle
from backtester.domain.trading import Signal

from backtester.strategies.base import SingleAssetStrategy
from backtester.strategies.calculators import RollingMaxCalculator, RollingMinCalculator


class DonchianBreakoutStrategy(SingleAssetStrategy):
    """Generate breakout signals from highs and lows of prior candles.

    A close strictly above the highest high in the previous ``entry_window``
    candles produces a buy signal. A close strictly below the lowest low in
    the previous ``exit_window`` candles produces a sell signal. The strategy
    holds until both channels contain a full window of observations.

    The current candle is added to the channels only after its signal is
    calculated, so its high or low cannot influence its own channel boundary.
    """

    def __init__(self,
        entry_window: int = 20,
        exit_window: int = 10,
        max_calc_factory: Callable[[int], RollingMaxCalculator] = lambda size: RollingMaxCalculator(size),
        min_calc_factory: Callable[[int], RollingMinCalculator] = lambda size: RollingMinCalculator(size)

    ) -> None:
        """Initialize the entry and exit channel window sizes."""

        if entry_window <= 0:
            raise ValueError("Positive integer expected for entry_window")
        if exit_window <= 0:
            raise ValueError("Positive integer expected for exit_window")

        self._max_calc = max_calc_factory(entry_window)
        self._min_calc = min_calc_factory(exit_window)
        self._prev_max = None
        self._prev_min = None

    def on_candle(self, candle: Candle) -> Signal:
        """Return a signal by comparing the close with the prior channels."""
        signal = Signal.HOLD

        if self._prev_max is not None and self._prev_min is not None:
            if candle.close > self._prev_max:
                signal = Signal.BUY
            elif candle.close < self._prev_min:
                signal = Signal.SELL

        self._prev_max = self._max_calc.next_value(candle.high)
        self._prev_min = self._min_calc.next_value(candle.low)
        return signal

    def reset(self) -> None:
        self._max_calc.reset()
        self._min_calc.reset()
        self._prev_max = None
        self._prev_min = None
