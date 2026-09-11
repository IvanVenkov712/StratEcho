from datetime import datetime
from unittest.mock import Mock

import pytest

from backtester.domain.trading import (
    MultiAssetSignal,
    OrderIntent,
    PendingDecision,
    RebalanceDecision,
    Side,
    Signal,
    SignalDecision,
    SizingInstruction,
    SizingMode,
    TargetAllocation,
)
from backtester.execution.decision_execution.decision_executor import DecisionExecutionResult
from backtester.execution.decision_execution.intent_executor import IntentExecutor
from backtester.execution.decision_execution.signal_decision_executor import (
    SignalDecisionExecutor,
    side_from_signal,
)
from backtester.sizing.asset_allocation import AssetAllocation
from backtester.sizing.policy import MultiAssetSizingPlan, SizingPlan


DECISION_TIME = datetime(2026, 1, 1)
EXECUTION_TIME = datetime(2026, 1, 2)


@pytest.fixture
def intent_executor() -> Mock:
    executor = Mock(spec=IntentExecutor)
    executor.execute.return_value = DecisionExecutionResult([], [])
    return executor


@pytest.fixture
def sizing() -> MultiAssetSizingPlan:
    return MultiAssetSizingPlan({
        "A": SizingPlan(
            buy=SizingInstruction(2, SizingMode.FIXED),
            sell=SizingInstruction(None, SizingMode.ALL_IN),
        ),
        "B": SizingPlan(
            buy=SizingInstruction(0.5, SizingMode.PERCENT),
            sell=SizingInstruction(3, SizingMode.UP_TO),
        ),
    })


@pytest.mark.parametrize(
    ("signals", "expected_sides", "expected_instructions"),
    [
        (
            {"A": Signal.BUY, "B": Signal.SELL}, [Side.BUY, Side.SELL],
            [SizingInstruction(2, SizingMode.FIXED), SizingInstruction(3, SizingMode.UP_TO)],
        ),
        (
            {"A": Signal.SELL, "B": Signal.BUY}, [Side.SELL, Side.BUY],
            [SizingInstruction(None, SizingMode.ALL_IN), SizingInstruction(0.5, SizingMode.PERCENT)],
        ),
    ],
)
def test_signal_creates_intents_with_symbol_sizing_and_separate_execution_time(
    intent_executor: Mock, sizing: MultiAssetSizingPlan, signals: dict[str, Signal],
    expected_sides: list[Side], expected_instructions: list[SizingInstruction],
) -> None:
    allocation = AssetAllocation({"A": 0.6, "B": 0.4})
    executor = SignalDecisionExecutor(intent_executor, sizing, allocation)
    decision = SignalDecision(DECISION_TIME, MultiAssetSignal(signals))
    prices = {"A": 20.0, "B": 50.0}

    result = executor.execute(decision, EXECUTION_TIME, prices)

    intent_executor.execute.assert_called_once_with(
        [
            OrderIntent("A", expected_sides[0], DECISION_TIME, expected_instructions[0]),
            OrderIntent("B", expected_sides[1], DECISION_TIME, expected_instructions[1]),
        ],
        EXECUTION_TIME, prices, allocation,
    )
    assert intent_executor.execute.call_args.args[3] is allocation
    assert result is intent_executor.execute.return_value
    assert decision.signal.signals == signals


@pytest.mark.parametrize(
    ("signals", "expected_intents"),
    [
        ({}, []),
        ({"A": Signal.HOLD, "B": Signal.HOLD}, []),
        ({"A": Signal.HOLD, "B": Signal.BUY}, [
            OrderIntent("B", Side.BUY, DECISION_TIME, SizingInstruction(0.5, SizingMode.PERCENT)),
        ]),
        ({"A": Signal.SELL}, [
            OrderIntent("A", Side.SELL, DECISION_TIME, SizingInstruction(None, SizingMode.ALL_IN)),
        ]),
    ],
    ids=["empty", "all-hold", "mixed-hold-and-buy", "partial-symbols"],
)
def test_signal_ignores_hold_and_allows_partial_or_empty_signals(
    intent_executor: Mock, sizing: MultiAssetSizingPlan,
    signals: dict[str, Signal], expected_intents: list[OrderIntent],
) -> None:
    allocation = AssetAllocation({"A": 0.5, "B": 0.5})
    executor = SignalDecisionExecutor(intent_executor, sizing, allocation)
    decision = SignalDecision(DECISION_TIME, MultiAssetSignal(signals))
    prices = {"A": 20.0, "B": 50.0}

    result = executor.execute(decision, EXECUTION_TIME, prices)

    intent_executor.execute.assert_called_once_with(expected_intents, EXECUTION_TIME, prices, allocation)
    assert result is intent_executor.execute.return_value


@pytest.mark.parametrize("weights", [{"A": 1.0}, {"A": 0.5, "B": 0.0, "C": 0.5}])
def test_signal_rejects_sizing_symbols_that_do_not_match_allocation(
    intent_executor: Mock, sizing: MultiAssetSizingPlan, weights: dict[str, float],
) -> None:
    with pytest.raises(ValueError, match="Sizing plan symbols do not match supported symbols"):
        SignalDecisionExecutor(intent_executor, sizing, AssetAllocation(weights))

    intent_executor.execute.assert_not_called()


@pytest.mark.parametrize("signal", [Signal.BUY, Signal.SELL, Signal.HOLD])
def test_signal_rejects_unsupported_symbol_even_for_hold(
    intent_executor: Mock, sizing: MultiAssetSizingPlan, signal: Signal,
) -> None:
    executor = SignalDecisionExecutor(intent_executor, sizing, AssetAllocation({"A": 0.5, "B": 0.5}))
    decision = SignalDecision(DECISION_TIME, MultiAssetSignal({"A": Signal.BUY, "C": signal}))

    with pytest.raises(ValueError, match="unsupported=\\['C'\\]"):
        executor.execute(decision, EXECUTION_TIME, {"A": 20.0, "B": 50.0})

    intent_executor.execute.assert_not_called()


@pytest.mark.parametrize("invalid_signal", [None, "buy", 1])
def test_signal_rejects_invalid_signal_without_submitting_partial_intents(
    intent_executor: Mock, sizing: MultiAssetSizingPlan, invalid_signal: object,
) -> None:
    executor = SignalDecisionExecutor(intent_executor, sizing, AssetAllocation({"A": 0.5, "B": 0.5}))
    decision = SignalDecision(DECISION_TIME, MultiAssetSignal({"A": Signal.BUY, "B": invalid_signal}))

    with pytest.raises(ValueError, match="Not a valid signal"):
        executor.execute(decision, EXECUTION_TIME, {"A": 20.0, "B": 50.0})

    intent_executor.execute.assert_not_called()


@pytest.mark.parametrize("decision", [
    PendingDecision(DECISION_TIME),
    RebalanceDecision(DECISION_TIME, TargetAllocation({})),
])
def test_signal_rejects_wrong_decision_type(
    intent_executor: Mock, sizing: MultiAssetSizingPlan, decision: PendingDecision,
) -> None:
    executor = SignalDecisionExecutor(intent_executor, sizing, AssetAllocation({"A": 0.5, "B": 0.5}))

    with pytest.raises(ValueError, match="SignalDecision is expected"):
        executor.execute(decision, EXECUTION_TIME, {})

    intent_executor.execute.assert_not_called()


def test_signal_propagates_intent_executor_error(
    intent_executor: Mock, sizing: MultiAssetSizingPlan,
) -> None:
    error = ValueError("Invalid execution input")
    intent_executor.execute.side_effect = error
    allocation = AssetAllocation({"A": 0.5, "B": 0.5})
    executor = SignalDecisionExecutor(intent_executor, sizing, allocation)
    decision = SignalDecision(DECISION_TIME, MultiAssetSignal({}))
    prices = {"A": 20.0, "B": 50.0}

    with pytest.raises(ValueError) as caught:
        executor.execute(decision, EXECUTION_TIME, prices)

    assert caught.value is error
    intent_executor.execute.assert_called_once_with([], EXECUTION_TIME, prices, allocation)


@pytest.mark.parametrize("symbols", [("A",), ("A", "C"), ("A", "B", "C"), ()])
def test_execute_rejects_incompatible_prices_even_for_empty_signals(
    intent_executor: Mock, sizing: MultiAssetSizingPlan, symbols: tuple[str, ...],
) -> None:
    executor = SignalDecisionExecutor(intent_executor, sizing, AssetAllocation({"A": 0.5, "B": 0.5}))
    decision = SignalDecision(DECISION_TIME, MultiAssetSignal({}))

    with pytest.raises(ValueError, match="Market data symbols do not match"):
        executor.execute(decision, EXECUTION_TIME, dict.fromkeys(symbols, 20.0))

    intent_executor.execute.assert_not_called()


def test_validating_signal_does_not_size_or_execute_orders(
    intent_executor: Mock, sizing: MultiAssetSizingPlan,
) -> None:
    executor = SignalDecisionExecutor(intent_executor, sizing, AssetAllocation({"A": 0.5, "B": 0.5}))
    decision = SignalDecision(DECISION_TIME, MultiAssetSignal({"A": Signal.BUY}))

    executor.validate_decision(decision, ("A", "B"))

    intent_executor.execute.assert_not_called()
    intent_executor.broker.portfolio.snapshot.assert_not_called()


@pytest.mark.parametrize(("signal", "expected_side"), [(Signal.BUY, Side.BUY), (Signal.SELL, Side.SELL)])
def test_side_from_signal_maps_buy_and_sell(signal: Signal, expected_side: Side) -> None:
    assert side_from_signal(signal) is expected_side


@pytest.mark.parametrize("signal", [Signal.HOLD, None, "buy"])
def test_side_from_signal_rejects_non_trading_signals(signal: object) -> None:
    with pytest.raises(ValueError, match="Invalid signal"):
        side_from_signal(signal)
