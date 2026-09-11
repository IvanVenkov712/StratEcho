from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

from backtester.domain.trading import TargetAllocation, PortfolioSnapshot, Order, OrderIntent, SizingMode
from backtester.sizing.policy import SizingPlan


@dataclass(frozen=True)
class RebalanceContext:
    execution_timestamp: datetime
    decision_timestamp: datetime
    target: TargetAllocation
    snapshot: PortfolioSnapshot
    prices: Mapping[str, float]

class RebalancePlanner(ABC):

    def __init__(
            self,
            sizing: Mapping[str, SizingMode]
    ):
        self._sizing = sizing

    @abstractmethod
    def get_intents(self, context: RebalanceContext) -> Sequence[Order]:
        pass