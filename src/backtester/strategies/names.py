"""Human-readable names for the concrete strategy types."""

from backtester.strategies.base import SingleAssetStrategy
from backtester.strategies.breakout import DonchianBreakoutStrategy
from backtester.strategies.buy_n_hold import BuyAndHoldStrategy
from backtester.strategies.moving_average import (
    ExponentialMovingAverageCrossStrategy,
    SimpleMovingAverageCrossStrategy,
)
from backtester.strategies.mrma import (
    ExponentialMeanReversionStrategy,
    SimpleMeanReversionStrategy,
)
from backtester.strategies.rsi_strategies import (
    CutlerRSIStrategy,
    ExponentialRSIStrategy,
    WilderRSIStrategy,
)


STRATEGY_NAMES: dict[type[SingleAssetStrategy], str] = {
    BuyAndHoldStrategy: "Buy and Hold",
    SimpleMovingAverageCrossStrategy: "Simple Moving Average Crossover",
    ExponentialMovingAverageCrossStrategy: "Exponential Moving Average Crossover",
    CutlerRSIStrategy: "Cutler RSI",
    ExponentialRSIStrategy: "Exponential RSI",
    WilderRSIStrategy: "Wilder RSI",
    SimpleMeanReversionStrategy: "Simple Mean Reversion",
    ExponentialMeanReversionStrategy: "Exponential Mean Reversion",
    DonchianBreakoutStrategy: "Donchian Breakout",
}
