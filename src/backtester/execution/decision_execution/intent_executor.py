from datetime import datetime
from typing import Sequence, Callable

from backtester.domain.trading import OrderIntent, Side, Order, OrderExecutionResult
from backtester.execution.broker import Broker
from backtester.execution.decision_execution.decision_executor import DecisionExecutionResult
from backtester.order_resolving.order_resolver import OrderResolver, OrderResolutionContext
from backtester.sizing.asset_allocation import AssetAllocation


class IntentExecutor:
    def __init__(
            self,
            resolver: OrderResolver,
            broker: Broker,
            priority: Callable[[str], int]
    ):
        self._broker = broker
        self._resolver = resolver
        self._priority = priority

    def execute(
            self,
            intents: Sequence[OrderIntent],
            timestamp: datetime,
            prices: dict[str, float],
            allocation: AssetAllocation,
    ) -> DecisionExecutionResult:

        """Resolve and execute intents sequentially at this frame's open.

        Sort by sells before buys, ascending priority, then symbol. Refresh the
        opening snapshot before every resolution: sale proceeds can fund later
        buys, and earlier fills change cash, holdings, and equity after costs.
        Consequently, later allocation budgets can depend on execution order.

        Only orders submitted to the broker produce execution results. Intents
        skipped by the resolver, including unaffordable fixed buys, are omitted.
        """

        sorted_intents = self._sorted_intents(intents)

        trades = []
        exec_results = []

        for intent in sorted_intents:
            order = self._create_order(intent, timestamp, prices, allocation)
            if order is not None:
                exec_result = self._execute_pending_order(order, timestamp, prices)
                exec_results.append(exec_result)
                if exec_result.trade is not None:
                    trades.append(exec_result.trade)

        return DecisionExecutionResult(exec_results, trades)

    def _sorted_intents(self, intents: Sequence[OrderIntent]) -> Sequence[OrderIntent]:
        def intent_key(intent: OrderIntent) -> tuple[int, int, str]:
            first = 0 if intent.side == Side.SELL else 1
            second = self._priority(intent.symbol)
            return first, second, intent.symbol

        sorted_intents = sorted(
            intents,
            key=intent_key
        )

        return sorted_intents

    def _create_order(
            self,
            intent: OrderIntent,
            timestamp: datetime,
            prices: dict[str, float],
            allocation: AssetAllocation,
    ) -> Order | None:

        context = self._create_order_resolution_context(timestamp, prices, allocation)

        return self._resolver.resolve(
            intent=intent,
            context=context
        )

    def _create_order_resolution_context(
            self,
            timestamp: datetime,
            prices: dict[str, float],
            allocation: AssetAllocation,
    ) -> OrderResolutionContext:
        """Value the current portfolio at frame opens after any earlier fills."""

        return OrderResolutionContext(
            timestamp=timestamp,
            reference_prices=prices,
            snapshot=self._broker.portfolio.snapshot(prices),
            allocation=allocation
        )

    def _execute_pending_order(
            self,
            order: Order,
            timestamp: datetime,
            prices: dict[str, float]
    ) -> OrderExecutionResult:
        return self._broker.execute(
            order=order,
            prices=prices,
            timestamp=timestamp
        )
