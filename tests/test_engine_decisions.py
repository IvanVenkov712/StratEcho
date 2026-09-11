"""Engine orchestration tests with mocked strategy and decision executor."""

from datetime import datetime, timedelta
from unittest.mock import Mock, call

import pytest

from backtester.domain.market import Candle, MarketFrame
from backtester.domain.trading import (
    MultiAssetSignal, Order, OrderExecutionResult, OrderExecutionStatus,
    PortfolioSnapshot, RebalanceDecision, Side, Signal, SignalDecision,
    TargetAllocation, Trade,
)
from backtester.engine.backtest import BacktestEngine
from backtester.execution.decision_execution.decision_executor import (
    DecisionExecutionResult, DecisionExecutor,
)
from backtester.strategies.portfolio_strategies.portfolio_strategy import PortfolioStrategy


START = datetime(2026, 1, 1)


def make_frame(day: int, opening: float, closing: float) -> MarketFrame:
    timestamp = START + timedelta(days=day)
    return MarketFrame(timestamp, {
        "A": Candle(timestamp, opening, max(opening, closing), min(opening, closing), closing, 10),
    })


@pytest.mark.parametrize("rebalance", [False, True], ids=["signal", "rebalance"])
def test_engine_executes_previous_decision_then_observes_and_validates_current_frame(rebalance: bool) -> None:
    first, second = make_frame(0, 20, 25), make_frame(1, 30, 35)
    if rebalance:
        decisions = [
            RebalanceDecision(first.timestamp, TargetAllocation({"A": 1.0})),
            RebalanceDecision(second.timestamp, TargetAllocation({})),
        ]
    else:
        decisions = [
            SignalDecision(first.timestamp, MultiAssetSignal({"A": Signal.BUY})),
            SignalDecision(second.timestamp, MultiAssetSignal({"A": Signal.SELL})),
        ]
    strategy = Mock(spec=PortfolioStrategy)
    strategy.on_frame.side_effect = decisions
    executor = Mock(spec=DecisionExecutor)
    executor.broker.portfolio.cash = 1000
    snapshots = [PortfolioSnapshot(1000, 1000, {}), PortfolioSnapshot(700, 1050, {"A": 10})]
    executor.broker.portfolio.snapshot.side_effect = snapshots
    order = Order("A", Side.BUY, 10, first.timestamp, second.timestamp)
    trade = Trade("A", Side.BUY, 10, 30, 0, second.timestamp)
    execution = OrderExecutionResult(OrderExecutionStatus.SUCCESS, order, trade)
    executor.execute.return_value = DecisionExecutionResult([execution], [trade])
    events = Mock()
    events.attach_mock(executor.broker.portfolio.snapshot, "snapshot")
    events.attach_mock(strategy.on_frame, "on_frame")
    events.attach_mock(executor.validate_decision, "validate")
    events.attach_mock(executor.execute, "execute")

    engine = BacktestEngine(strategy, executor, [first, second])
    result = engine.run()

    assert events.mock_calls == [
        call.snapshot(prices={"A": 25}),
        call.on_frame(first, snapshots[0]),
        call.validate(decisions[0], ("A",)),
        call.execute(decisions[0], second.timestamp, {"A": 30}),
        call.snapshot(prices={"A": 35}),
        call.on_frame(second, snapshots[1]),
        call.validate(decisions[1], ("A",)),
    ]
    executor.validate_universe.assert_called_once_with(("A",), source=f"Frame at {first.timestamp}")
    assert result.symbols == ("A",)
    assert [record.generated_decision for record in result.records] == decisions
    assert [record.snapshot for record in result.records] == snapshots
    assert result.order_executions == [execution]
    assert result.trades == [trade]
    assert result.initial_cash == 1000
    assert engine.run() is result
    assert executor.execute.call_count == 1
    assert strategy.on_frame.call_count == 2


def test_empty_run_does_not_observe_validate_or_execute_decisions() -> None:
    strategy = Mock(spec=PortfolioStrategy)
    executor = Mock(spec=DecisionExecutor)
    executor.broker.portfolio.cash = 1000

    engine = BacktestEngine(strategy, executor, [])
    result = engine.run()

    assert result.symbols == ()
    assert result.initial_cash == 1000
    assert result.records == result.trades == result.order_executions == []
    strategy.on_frame.assert_not_called()
    executor.validate_decision.assert_not_called()
    executor.validate_universe.assert_not_called()
    executor.execute.assert_not_called()
    executor.broker.portfolio.snapshot.assert_not_called()
    assert engine.run() is result


def test_validation_error_on_final_frame_propagates_without_execution() -> None:
    frame = make_frame(0, 20, 25)
    strategy = Mock(spec=PortfolioStrategy)
    decision = SignalDecision(frame.timestamp, MultiAssetSignal({"A": "invalid"}))
    strategy.on_frame.return_value = decision
    executor = Mock(spec=DecisionExecutor)
    executor.broker.portfolio.cash = 1000
    error = ValueError("Invalid decision")
    executor.validate_decision.side_effect = error

    with pytest.raises(ValueError) as caught:
        BacktestEngine(strategy, executor, [frame]).run()

    assert caught.value is error
    executor.validate_decision.assert_called_once_with(decision, ("A",))
    executor.execute.assert_not_called()


def test_incompatible_executor_universe_fails_before_strategy_or_execution() -> None:
    strategy = Mock(spec=PortfolioStrategy)
    executor = Mock(spec=DecisionExecutor)
    executor.validate_universe.side_effect = ValueError("Incompatible universe")

    with pytest.raises(ValueError, match="Incompatible universe"):
        BacktestEngine(strategy, executor, [make_frame(0, 20, 25)])

    strategy.on_frame.assert_not_called()
    executor.execute.assert_not_called()
    executor.broker.portfolio.snapshot.assert_not_called()
