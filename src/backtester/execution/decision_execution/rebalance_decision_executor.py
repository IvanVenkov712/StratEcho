from datetime import datetime
from collections.abc import Collection
from typing import cast

from backtester.data.validation import validate_symbols
from backtester.domain.trading import PendingDecision, RebalanceDecision
from backtester.execution.decision_execution.decision_executor import DecisionExecutor, DecisionExecutionResult
from backtester.execution.decision_execution.intent_executor import IntentExecutor
from backtester.rebalance.rebalance_planner import RebalancePlanner, RebalanceContext
from backtester.sizing.asset_allocation import AssetAllocation


class RebalanceDecisionExecutor(DecisionExecutor):

    def __init__(
            self,
            rebalance_planner: RebalancePlanner,
            intent_executor: IntentExecutor
    ):
        super().__init__(intent_executor.broker)
        self._planner = rebalance_planner
        self._intent_executor = intent_executor

    def validate_decision(self, decision: PendingDecision, symbols: Collection[str]) -> None:
        """Require every target symbol to belong to the observed market universe."""
        if not isinstance(decision, RebalanceDecision):
            raise ValueError("RebalanceDecision is expected")
        validate_symbols(
            decision.target.weights, symbols,
            source=f"Rebalance target at {decision.timestamp}", require_all=False,
        )

    def execute(
            self,
            pending_decision: PendingDecision,
            timestamp: datetime,
            prices: dict[str, float]
    ) -> DecisionExecutionResult:
        self.validate_decision(pending_decision, prices.keys())

        rebalance_decision = cast(RebalanceDecision, pending_decision)
        snapshot = self.broker.portfolio.snapshot(prices)

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
