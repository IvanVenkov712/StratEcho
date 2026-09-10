from abc import ABC, abstractmethod
from typing import Mapping, Sequence

from backtester.domain.trading import TargetAllocation, PortfolioSnapshot, Order


class RebalancePlanner(ABC):

    @abstractmethod
    def get_orders(
        self,
        target: TargetAllocation,
        snapshot: PortfolioSnapshot,
        prices: Mapping[str, float]
    ) -> Sequence[Order]:
        pass