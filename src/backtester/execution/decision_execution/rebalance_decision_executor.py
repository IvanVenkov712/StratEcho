from datetime import datetime
from typing import Callable

from backtester.domain.trading import PendingDecision, RebalanceDecision
from backtester.execution.broker import Broker
from backtester.execution.decision_execution.decision_executor import DecisionExecutor, DecisionExecutionResult
from backtester.execution.decision_execution.intent_executor import IntentExecutor
from backtester.rebalance.rebalance_planner import RebalancePlanner, RebalanceContext
from backtester.sizing.asset_allocation import AssetAllocation


class RebalanceDecisionExecutor(DecisionExecutor):

    def __init__(
            self,
            broker: Broker,
            rebalance_planner: RebalancePlanner,
            priority: Callable[[str], int],
            intent_executor: IntentExecutor
    ):
        self._broker = broker
        self._planner = rebalance_planner
        self._priority = priority
        self._intent_executor = intent_executor

    def execute(
            self,
            pending_decision: PendingDecision,
            timestamp: datetime,
            prices: dict[str, float]
    ) -> DecisionExecutionResult:
        if not isinstance(pending_decision, RebalanceDecision):
            raise ValueError("RebalanceDecision is expected")

        rebalance_decision: RebalanceDecision = pending_decision

        intents = self._planner.get_intents(
            RebalanceContext(
                execution_timestamp=timestamp,
                decision_timestamp=rebalance_decision.timestamp,
                target=rebalance_decision.target,
                snapshot=self._broker.portfolio.snapshot(prices),
                prices=prices
            )
        )
        allocation = AssetAllocation(
            allocations=dict(rebalance_decision.target.weights)
        )
        return self._intent_executor.execute(intents, timestamp, prices, allocation)
