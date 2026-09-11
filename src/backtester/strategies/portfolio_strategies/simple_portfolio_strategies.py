from collections.abc import Mapping

from backtester.domain.market import MarketFrame
from backtester.domain.trading import PortfolioSnapshot, PendingDecision, RebalanceDecision, TargetAllocation
from backtester.strategies.portfolio_strategies.portfolio_strategy import PortfolioStrategy


class EqualWeightStrategy(PortfolioStrategy):
    """Request equal weights across a non-empty universe on every frame."""

    def __init__(self, asset_universe: frozenset[str]):
        if not asset_universe:
            raise ValueError("Asset universe must not be empty")
        self._universe = asset_universe

    def on_frame(self, frame: MarketFrame, snapshot: PortfolioSnapshot) -> PendingDecision:
        n = len(self._universe)
        weight = 1.0 / n

        return RebalanceDecision(
            frame.timestamp,
            TargetAllocation(
                {
                    symbol: weight for symbol in self._universe
                }
            )
        )


class PresetWeightStrategy(PortfolioStrategy):
    """Request fixed weights on every frame; the remainder represents cash."""

    def __init__(self, weights: Mapping[str, float]):
        if not all(0 <= weight <= 1 for weight in weights.values()):
            raise ValueError("Weights must be in [0, 1]")

        if sum(weights.values()) > 1:
            raise ValueError("weights sum must not exceed 1")

        self._weights = dict(weights)

    def on_frame(self, frame: MarketFrame, snapshot: PortfolioSnapshot) -> PendingDecision:
        return RebalanceDecision(
            frame.timestamp,
            TargetAllocation(self._weights)
        )
