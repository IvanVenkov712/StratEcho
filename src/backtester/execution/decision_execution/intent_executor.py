from datetime import datetime
from typing import Sequence

from backtester.domain.trading import OrderIntent
from backtester.execution.broker import Broker
from backtester.execution.decision_execution.decision_executor import DecisionExecutionResult
from backtester.order_resolving.order_resolver import OrderResolver
from backtester.sizing.asset_allocation import AssetAllocation


class IntentExecutor:
    def __init__(
            self,
            resolver: OrderResolver,
            broker: Broker,
    ):
        self._broker = broker
        self._resolver = resolver

    def execute(
            self,
            intents: Sequence[OrderIntent],
            timestamp: datetime,
            prices: dict[str, float],
            allocation: AssetAllocation,
    ) -> DecisionExecutionResult:
