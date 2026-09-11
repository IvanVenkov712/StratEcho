from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

from backtester.domain.trading import TargetAllocation, PortfolioSnapshot, Order

@dataclass(frozen=True)
class RebalanceContext:
    execution_timestamp: datetime
    decision_timestamp: datetime
    target: TargetAllocation
    snapshot: PortfolioSnapshot
    prices: Mapping[str, float]

class RebalancePlanner(ABC):

    @abstractmethod
    def get_orders(self, context: RebalanceContext) -> Sequence[Order]:
        pass