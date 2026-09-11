from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence, Callable

from backtester.data.validation import validate_symbols
from backtester.domain.trading import OrderExecutionResult, Trade, PendingDecision, OrderIntent, Side, Order, Signal, \
    MultiAssetSignal, SignalDecision
from backtester.execution.broker import Broker
from backtester.order_resolving.order_resolver import OrderResolver, OrderResolutionContext
from backtester.sizing.asset_allocation import AssetAllocation
from backtester.sizing.policy import MultiAssetSizingPlan


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
