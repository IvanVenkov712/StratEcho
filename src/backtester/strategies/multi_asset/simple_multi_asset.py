from typing import Callable

from backtester.domain.market import MarketFrame
from backtester.domain.trading import MultiAssetSignal, Signal
from backtester.strategies.base import SingleAssetStrategy
from backtester.strategies.multi_asset.base import MultiAssetStrategy


class SimpleMultiAssetStrategy(MultiAssetStrategy):

    def __init__(self, strategies: dict[str, SingleAssetStrategy]):
        self._strategies = strategies

    def on_frame(self, frame: MarketFrame) -> MultiAssetSignal:
        signals = {
            symbol: strat.on_candle(frame.candles[symbol])
            for symbol, strat in self._strategies.items()
        }
        return MultiAssetSignal(signals)

    def reset(self) -> None:
        for strategy in self._strategies.values():
            strategy.reset()

class SameForAll(SimpleMultiAssetStrategy):
    def __init__(self,
        symbols: set[str],
        supplier: Callable[[], SingleAssetStrategy]
    ):
        strategies = {
            symbol: supplier()
            for symbol in symbols
        }
        super().__init__(strategies)