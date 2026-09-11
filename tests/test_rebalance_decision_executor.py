from datetime import datetime
from unittest.mock import Mock

import pytest

from backtester.domain.trading import (
    MultiAssetSignal, OrderIntent, PendingDecision, PortfolioSnapshot,
    RebalanceDecision, Side, SignalDecision, SizingInstruction, SizingMode,
    TargetAllocation,
)
from backtester.execution.broker import Broker
from backtester.domain.market import Candle, MarketFrame
from backtester.engine.backtest import BacktestEngine
from backtester.execution.decision_execution.decision_executor import DecisionExecutionResult
from backtester.execution.decision_execution.intent_executor import IntentExecutor
from backtester.execution.decision_execution.rebalance_decision_executor import RebalanceDecisionExecutor
from backtester.rebalance.rebalance_planner import RebalanceContext, RebalancePlanner
from backtester.sizing.asset_allocation import AssetAllocation
from backtester.strategies.portfolio_strategies.portfolio_strategy import PortfolioStrategy


DECISION_TIME = datetime(2026, 1, 1)
EXECUTION_TIME = datetime(2026, 1, 2)


@pytest.mark.parametrize(
    ("positions", "target_weights", "expected_weights"),
    [
        ({"A": 10}, {"B": 1.0}, {"A": 0.0, "B": 1.0}),
        ({"A": 10}, {}, {"A": 0.0}),
        ({"A": 10}, {"A": 0.5, "B": 0.5}, {"A": 0.5, "B": 0.5}),
        ({"A": 10}, {"A": 0.0, "B": 0.5}, {"A": 0.0, "B": 0.5}),
        ({}, {"B": 1.0}, {"B": 1.0}),
        ({}, {}, {}),
    ],
)
def test_rebalance_allocation_includes_holdings_and_preserves_explicit_targets(
    positions: dict[str, int], target_weights: dict[str, float],
    expected_weights: dict[str, float],
) -> None:
    prices = {"A": 100.0, "B": 100.0}
    broker = Mock(spec=Broker)
    snapshot = PortfolioSnapshot(1000.0, 1000.0 + sum(positions.values()) * 100.0, dict(positions))
    broker.portfolio.snapshot.return_value = snapshot
    planner = Mock(spec=RebalancePlanner)
    intents = [
        OrderIntent(symbol, Side.SELL, DECISION_TIME, SizingInstruction(None, SizingMode.ALL_IN))
        for symbol in positions
    ]
    planner.get_intents.return_value = intents
    intent_executor = Mock(spec=IntentExecutor)
    expected_result = DecisionExecutionResult([], [])
    intent_executor.execute.return_value = expected_result
    intent_executor.broker = broker
    executor = RebalanceDecisionExecutor(planner, intent_executor)
    decision = RebalanceDecision(DECISION_TIME, TargetAllocation(target_weights))

    result = executor.execute(decision, EXECUTION_TIME, prices)

    assert result is expected_result
    broker.portfolio.snapshot.assert_called_once_with(prices)
    planner.get_intents.assert_called_once_with(RebalanceContext(
        execution_timestamp=EXECUTION_TIME,
        decision_timestamp=DECISION_TIME,
        target=decision.target,
        snapshot=snapshot,
        prices=prices,
    ))
    intent_executor.execute.assert_called_once_with(
        intents, EXECUTION_TIME, prices, AssetAllocation(expected_weights),
    )
    assert intent_executor.execute.call_args.args[0] is intents
    assert decision.target.weights == target_weights
    assert snapshot.positions == positions
    broker.execute.assert_not_called()


@pytest.mark.parametrize("decision", [
    PendingDecision(DECISION_TIME),
    SignalDecision(DECISION_TIME, MultiAssetSignal({})),
])
def test_rebalance_rejects_wrong_decision_type_before_calling_dependencies(
    decision: PendingDecision,
) -> None:
    broker = Mock(spec=Broker)
    planner = Mock(spec=RebalancePlanner)
    intent_executor = Mock(spec=IntentExecutor)
    intent_executor.broker = broker
    executor = RebalanceDecisionExecutor(planner, intent_executor)

    with pytest.raises(ValueError, match="RebalanceDecision is expected"):
        executor.execute(decision, EXECUTION_TIME, {})

    broker.portfolio.snapshot.assert_not_called()
    planner.get_intents.assert_not_called()
    intent_executor.execute.assert_not_called()


def test_rebalance_delegates_empty_plan_for_existing_holdings() -> None:
    broker = Mock(spec=Broker)
    broker.portfolio.snapshot.return_value = PortfolioSnapshot(0.0, 1000.0, {"A": 10})
    planner = Mock(spec=RebalancePlanner)
    planner.get_intents.return_value = []
    intent_executor = Mock(spec=IntentExecutor)
    intent_executor.execute.return_value = DecisionExecutionResult([], [])
    intent_executor.broker = broker
    executor = RebalanceDecisionExecutor(planner, intent_executor)
    decision = RebalanceDecision(DECISION_TIME, TargetAllocation({"A": 1.0}))

    result = executor.execute(decision, EXECUTION_TIME, {"A": 100.0})

    intent_executor.execute.assert_called_once_with(
        [], EXECUTION_TIME, {"A": 100.0}, AssetAllocation({"A": 1.0}),
    )
    assert result is intent_executor.execute.return_value


@pytest.mark.parametrize("failing_dependency", ["snapshot", "planner", "intent_executor"])
def test_rebalance_propagates_dependency_errors(failing_dependency: str) -> None:
    broker = Mock(spec=Broker)
    broker.portfolio.snapshot.return_value = PortfolioSnapshot(1000.0, 1000.0, {})
    planner = Mock(spec=RebalancePlanner)
    planner.get_intents.return_value = []
    intent_executor = Mock(spec=IntentExecutor)
    error = ValueError("Invalid rebalance input")
    dependency = {
        "snapshot": broker.portfolio.snapshot,
        "planner": planner.get_intents,
        "intent_executor": intent_executor.execute,
    }[failing_dependency]
    dependency.side_effect = error
    intent_executor.broker = broker
    executor = RebalanceDecisionExecutor(planner, intent_executor)
    decision = RebalanceDecision(DECISION_TIME, TargetAllocation({}))

    with pytest.raises(ValueError) as caught:
        executor.execute(decision, EXECUTION_TIME, {})

    assert caught.value is error
    broker.portfolio.snapshot.assert_called_once_with({})
    assert planner.get_intents.call_count == (0 if failing_dependency == "snapshot" else 1)
    assert intent_executor.execute.call_count == (1 if failing_dependency == "intent_executor" else 0)
    broker.execute.assert_not_called()


@pytest.mark.parametrize("weights", [{"C": 1.0}, {"A": 0.5, "C": 0.0}])
def test_rebalance_rejects_unpriced_targets_before_planning(weights: dict[str, float]) -> None:
    planner = Mock(spec=RebalancePlanner)
    intent_executor = Mock(spec=IntentExecutor)
    executor = RebalanceDecisionExecutor(planner, intent_executor)
    decision = RebalanceDecision(DECISION_TIME, TargetAllocation(weights))

    with pytest.raises(ValueError, match="Rebalance target.*unsupported=.*C"):
        executor.execute(decision, EXECUTION_TIME, {"A": 100.0, "B": 100.0})

    planner.get_intents.assert_not_called()
    intent_executor.execute.assert_not_called()
    intent_executor.broker.portfolio.snapshot.assert_not_called()


@pytest.mark.parametrize("weights", [{}, {"A": 1.0}, {"A": 0.25, "B": 0.5}])
def test_validating_rebalance_accepts_partial_targets_without_planning(weights: dict[str, float]) -> None:
    planner = Mock(spec=RebalancePlanner)
    intent_executor = Mock(spec=IntentExecutor)
    executor = RebalanceDecisionExecutor(planner, intent_executor)

    executor.validate_decision(RebalanceDecision(DECISION_TIME, TargetAllocation(weights)), ("A", "B"))

    planner.get_intents.assert_not_called()
    intent_executor.execute.assert_not_called()
    intent_executor.broker.portfolio.snapshot.assert_not_called()


@pytest.mark.parametrize("invalid", [False, True])
def test_engine_validates_final_rebalance_without_planning_orders(invalid: bool) -> None:
    frame = MarketFrame(DECISION_TIME, {"A": Candle(DECISION_TIME, 100, 100, 100, 100, 10)})
    strategy = Mock(spec=PortfolioStrategy)
    decision = RebalanceDecision(DECISION_TIME, TargetAllocation({"C" if invalid else "A": 1.0}))
    strategy.on_frame.return_value = decision
    planner = Mock(spec=RebalancePlanner)
    intent_executor = Mock(spec=IntentExecutor)
    intent_executor.broker.portfolio.cash = 1000
    intent_executor.broker.portfolio.snapshot.return_value = PortfolioSnapshot(1000, 1000, {})
    executor = RebalanceDecisionExecutor(planner, intent_executor)
    engine = BacktestEngine(strategy, executor, [frame])

    if invalid:
        with pytest.raises(ValueError, match="Rebalance target.*unsupported=.*C"):
            engine.run()
    else:
        result = engine.run()
        assert result.symbols == ("A",)
        assert result.records[0].generated_decision == decision
        assert result.trades == result.order_executions == []

    planner.get_intents.assert_not_called()
    intent_executor.execute.assert_not_called()
