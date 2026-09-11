from datetime import datetime
from typing import Callable, Sequence

from backtester.domain.trading import PendingDecision, RebalanceDecision, Order, Side
from backtester.execution.broker import Broker
from backtester.execution.decision_execution.decision_executor import DecisionExecutor, DecisionExecutionResult
from backtester.rebalance.rebalance_planner import RebalancePlanner, RebalanceContext


class RebalanceDecisionExecutor(DecisionExecutor):

    def __init__(
            self,
            broker: Broker,
            rebalance_planner: RebalancePlanner,
            priority: Callable[[str], int],
    ):
        self._broker = broker
        self._planner = rebalance_planner
        self._priority = priority

    def execute(
            self,
            pending_decision: PendingDecision,
            timestamp: datetime,
            prices: dict[str, float]
    ) -> DecisionExecutionResult:
        if not isinstance(pending_decision, RebalanceDecision):
            raise ValueError("RebalanceDecision is expected")

        rebalance_decision: RebalanceDecision = pending_decision

        orders = self._planner.get_orders(
            RebalanceContext(
                execution_timestamp=timestamp,
                decision_timestamp=rebalance_decision.timestamp,
                target=rebalance_decision.target,
                snapshot=self._broker.portfolio.snapshot(prices),
                prices=prices
            )
        )

        sorted_orders = self.sort_orders(orders)
        return self._execute_orders(sorted_orders, prices, timestamp)

    def sort_orders(self, orders: Sequence[Order]) -> Sequence[Order]:

        def order_key(order: Order) -> tuple[int, int, str]:
            first = 0 if order.side is Side.SELL else 1
            second = self._priority(order.symbol)
            third = order.symbol
            return first, second, third

        return sorted(orders, key=order_key)


    def _execute_orders(
            self,
            orders: Sequence[Order],
            prices: dict[str, float],
            timestamp: datetime
    ) -> DecisionExecutionResult:

        results = []
        trades = []
        for order in orders:
            result = self._broker.execute(order, prices, timestamp)
            results.append(result)
            if result.trade is not None:
                trades.append(result.trade)

        return DecisionExecutionResult(results, trades)