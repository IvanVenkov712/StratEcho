from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from backtester.domain.trading import OrderExecutionResult, Trade, PendingDecision


@dataclass(frozen=True)
class DecisionExecutionResult:
    order_executions: Sequence[OrderExecutionResult]
    trades: Sequence[Trade]


class DecisionExecutor(ABC):

    @abstractmethod
    def execute(
            self,
            pending_decision: PendingDecision,
            timestamp: datetime,
            prices: dict[str, float]
    ) -> DecisionExecutionResult:
        pass
