from abc import ABC, abstractmethod
from collections.abc import Collection
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
    """Validate strategy decisions separately from their later execution."""

    def __init__(self, broker: Broker):
        self._broker = broker

    @property
    def broker(self) -> Broker:
        return self._broker

    def validate_universe(self, symbols: Collection[str], *, source: str = "Market data") -> None:
        """Check data against fixed configuration, if the executor has any.

        Executors with dynamic allocation targets accept the data's universe.
        """

    @abstractmethod
    def validate_decision(self, decision: PendingDecision, symbols: Collection[str]) -> None:
        """Reject invalid decisions without planning, sizing, or executing orders."""

    @abstractmethod
    def execute(
            self,
            pending_decision: PendingDecision,
            timestamp: datetime,
            prices: dict[str, float]
    ) -> DecisionExecutionResult:
        pass
