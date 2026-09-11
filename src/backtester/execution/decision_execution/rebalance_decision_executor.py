from datetime import datetime

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
            intent_executor: IntentExecutor
    ):
        self._broker = broker
        self._planner = rebalance_planner
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
        snapshot = self._broker.portfolio.snapshot(prices)

        intents = self._planner.get_intents(
            RebalanceContext(
                execution_timestamp=timestamp,
                decision_timestamp=rebalance_decision.timestamp,
                target=rebalance_decision.target,
                snapshot=snapshot,
                prices=prices
            )
        )
        # The resolver needs a weight even for sales of omitted holdings.
        weights = dict.fromkeys(snapshot.positions, 0.0)
        weights.update(rebalance_decision.target.weights)
        allocation = AssetAllocation(allocations=weights)
        return self._intent_executor.execute(intents, timestamp, prices, allocation)
