from abc import ABC, abstractmethod

from backtester.domain.market import MarketFrame
from backtester.domain.trading import PortfolioSnapshot, PendingDecision, SignalDecision
from backtester.strategies.multi_asset.base import MultiAssetStrategy


class PortfolioStrategy(ABC):

    @abstractmethod
    def on_frame(self, frame: MarketFrame, snapshot: PortfolioSnapshot) -> PendingDecision:
        pass

class MultiAssetPortfolioStrategy(PortfolioStrategy):
    def __init__(self, strategy: MultiAssetStrategy):
        self._strategy = strategy

    def on_frame(self, frame: MarketFrame, snapshot: PortfolioSnapshot) -> PendingDecision:
        signal = self._strategy.on_frame(frame)
        decision = SignalDecision(frame.timestamp, signal)
        return decision
