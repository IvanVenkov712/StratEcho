from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from backtester.domain.trading import OrderExecutionResult, Trade, PendingDecision
from backtester.execution.broker import Broker


@dataclass(frozen=True)
class DecisionExecutionResult:
    order_executions: Sequence[OrderExecutionResult]
    trades: Sequence[Trade]


class DecisionExecutor(ABC):
    def __init__(self, broker: Broker):
        self._broker = broker

    @property
    def broker(self) -> Broker:
        return self._broker

    @abstractmethod
    def execute(
            self,
            pending_decision: PendingDecision,
            timestamp: datetime,
            prices: dict[str, float]
    ) -> DecisionExecutionResult:
        pass
