from typing import Callable

from backtester.data.validation import validate_symbols
from backtester.domain.market import MarketFrame
from backtester.domain.trading import MultiAssetSignal
from backtester.strategies.base import SingleAssetStrategy
from backtester.strategies.multi_asset.base import MultiAssetStrategy


class SimpleMultiAssetStrategy(MultiAssetStrategy):
    """Dispatch candles to distinct strategy instances owned by each symbol."""

    def __init__(self, strategies: dict[str, SingleAssetStrategy]):
        self._strategies = dict(strategies)
        owners: dict[int, str] = {}
        for symbol, strategy in self._strategies.items():
            identity = id(strategy)
            if identity in owners:
                raise ValueError(
                    f"Symbols {owners[identity]!r} and {symbol!r} share a strategy "
                    "instance; each symbol must have its own strategy instance."
                )
            owners[identity] = symbol

    def on_frame(self, frame: MarketFrame) -> MultiAssetSignal:
        validate_symbols(
            self._strategies,
            frame.candles,
            source=f"Strategy input at {frame.timestamp}",
            require_all=False,
        )
        signals = {
            symbol: strat.on_candle(frame.candles[symbol])
            for symbol, strat in self._strategies.items()
        }
        return MultiAssetSignal(signals)

    def reset(self) -> None:
        for strategy in self._strategies.values():
            strategy.reset()

class SameForAll(SimpleMultiAssetStrategy):
    """Call the supplier once per symbol; it must return a fresh instance."""

    def __init__(self,
        symbols: set[str],
        supplier: Callable[[], SingleAssetStrategy]
    ):
        strategies = {
            symbol: supplier()
            for symbol in symbols
        }
        super().__init__(strategies)
