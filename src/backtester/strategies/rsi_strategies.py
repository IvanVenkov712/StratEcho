"""relative strength index strategy."""

from typing import Callable

from backtester.domain.market import Candle
from backtester.domain.trading import Signal
from backtester.strategies.base import SingleAssetStrategy
from backtester.strategies.calculators import RSICalculator, CutlerRSICalculator, ExponentialRSICalculator, \
    WilderRSICalculator


# class RSICalculator(ABC):
#     @abstractmethod
#     def calculate_rsi(self, curr_price: float) -> float:
#         pass
#
#     @abstractmethod
#     def reset(self):
#         pass
#
# class SimpleRSICalculator(RSICalculator):
#     def __init__(self, n: int):
#         if n <= 0:
#             raise ValueError("Expected positive integer")
#
#         self._n = n
#         self._prices: list[float] = []
#
#     def calculate_rsi(self, curr_price: float) -> float:
#         self._prices.append(curr_price)
#         return calculate_simple_rsi(self._n, self._prices)
#
#     def reset(self):
#         self._prices.clear()
#
#
# def calculate_simple_rsi(n: int, prices: Sequence[float]) -> float:
#     """Calculate RSI from simple average gains and losses over ``n`` changes."""
#
#     deltas = [
#         curr - prev for
#         prev, curr in zip(prices[-n - 1:], prices[-n:])
#     ]
#
#     avg_gain = sum(max(delta, 0) for delta in deltas) / n
#     avg_loss = sum(max(-delta, 0) for delta in deltas) / n
#
#     if isclose(avg_loss, 0):
#         if isclose(avg_gain, 0):
#             return 50
#         return 100
#
#     rs = avg_gain / avg_loss
#
#     rsi = 100 - (100 / (1 + rs))
#
#     return rsi

class RSIStrategy(SingleAssetStrategy):
    """Buy below the lower RSI threshold and sell above the upper threshold."""

    def __init__(self,
                 factory: Callable[[int], RSICalculator],
                 min: float= 30,
                 max: float= 70,
                 window_size: int = 14):

        if not 0 <= min <= max <= 100:
            raise ValueError("0 <= min <= max <= 100")

        if not (isinstance(window_size, int) and not isinstance(window_size, bool) and window_size > 1):
            raise ValueError("positive integer is expected for window size")

        self._min: float = min
        self._max: float = max
        self._calculator = factory(window_size)

    def on_candle(self, candle: Candle) -> Signal:
        """Generate a threshold signal from the latest RSI value calculated with the RSICalculator."""

        rsi = self._calculator.next_value(candle.close)
        if rsi is None:
            return Signal.HOLD

        if rsi < self._min:
            return Signal.BUY
        elif rsi > self._max:
            return Signal.SELL
        else:
            return Signal.HOLD

    def reset(self):
        self._calculator.reset()


class CutlerRSIStrategy(RSIStrategy):
    def __init__(self,
                 min: float= 30,
                 max: float= 70,
                 window_size: int = 14):

        super().__init__(
            lambda size: CutlerRSICalculator(size),
            min,
            max,
            window_size
        )


class ExponentialRSIStrategy(RSIStrategy):
    def __init__(self,
                 min: float = 30,
                 max: float = 70,
                 window_size: int = 14):

        super().__init__(
            lambda size: ExponentialRSICalculator(size),
            min,
            max,
            window_size
        )

class WilderRSIStrategy(RSIStrategy):
    def __init__(self,
                 min: float = 30,
                 max: float = 70,
                 window_size: int = 14):
        super().__init__(
            lambda size: WilderRSICalculator(size),
            min,
            max,
            window_size
        )