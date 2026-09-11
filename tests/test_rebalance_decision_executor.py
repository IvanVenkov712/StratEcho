from datetime import datetime
from unittest.mock import Mock

import pytest

from backtester.domain.trading import (
    OrderIntent, PortfolioSnapshot, RebalanceDecision, Side,
    SizingInstruction, SizingMode, TargetAllocation,
)
from backtester.execution.broker import Broker
from backtester.execution.decision_execution.decision_executor import DecisionExecutionResult
from backtester.execution.decision_execution.intent_executor import IntentExecutor
from backtester.execution.decision_execution.rebalance_decision_executor import RebalanceDecisionExecutor
from backtester.rebalance.rebalance_planner import RebalancePlanner


@pytest.mark.parametrize(
    ("target_weights", "expected_weights"),
    [
        ({"B": 1.0}, {"A": 0.0, "B": 1.0}),
        ({}, {"A": 0.0}),
        ({"A": 0.5, "B": 0.5}, {"A": 0.5, "B": 0.5}),
    ],
)
def test_rebalance_allocation_includes_holdings_and_preserves_explicit_targets(
    target_weights: dict[str, float], expected_weights: dict[str, float],
) -> None:
    decision_time = datetime(2026, 1, 1)
    execution_time = datetime(2026, 1, 2)
    prices = {"A": 100.0, "B": 100.0}
    broker = Mock(spec=Broker)
    broker.portfolio.snapshot.return_value = PortfolioSnapshot(0.0, 1000.0, {"A": 10})
    planner = Mock(spec=RebalancePlanner)
    intents = [OrderIntent(
        "A", Side.SELL, decision_time, SizingInstruction(None, SizingMode.ALL_IN),
    )]
    planner.get_intents.return_value = intents
    intent_executor = Mock(spec=IntentExecutor)
    expected_result = DecisionExecutionResult([], [])
    intent_executor.execute.return_value = expected_result
    executor = RebalanceDecisionExecutor(broker, planner, intent_executor)
    decision = RebalanceDecision(decision_time, TargetAllocation(target_weights))

    result = executor.execute(decision, execution_time, prices)

    assert result is expected_result
    intent_executor.execute.assert_called_once()
    passed_intents, passed_time, passed_prices, allocation = intent_executor.execute.call_args.args
    assert passed_intents == intents
    assert passed_time == execution_time
    assert passed_prices == prices
    assert allocation.allocations == expected_weights
    assert decision.target.weights == target_weights
