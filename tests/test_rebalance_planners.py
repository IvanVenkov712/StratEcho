from dataclasses import replace
from datetime import datetime

import pytest

from backtester.domain.trading import (
    OrderIntent, PortfolioSnapshot, Side, SizingInstruction, SizingMode, TargetAllocation,
)
from backtester.rebalance.rebalance_planner import RebalanceContext
from backtester.rebalance.simple_rebalance_planners import FullRebalancePlanner, ThresholdRebalancePlanner


DECISION_TIME = datetime(2026, 1, 1)
EXECUTION_TIME = datetime(2026, 1, 2)


def make_context(
    cash: float = 0,
    positions: dict[str, int] | None = None,
    weights: dict[str, float] | None = None,
) -> RebalanceContext:
    positions = {"A": 30, "B": 40} if positions is None else positions
    weights = {"A": 0.5, "B": 0.5} if weights is None else weights
    prices = {"A": 20.0, "B": 10.0}
    value = cash + sum(quantity * prices[symbol] for symbol, quantity in positions.items())
    return RebalanceContext(
        EXECUTION_TIME, DECISION_TIME, TargetAllocation(weights),
        PortfolioSnapshot(cash, value, positions), prices,
    )


def intent(symbol: str, side: Side, quantity: int, mode: SizingMode = SizingMode.UP_TO) -> OrderIntent:
    return OrderIntent(symbol, side, DECISION_TIME, SizingInstruction(quantity, mode))


@pytest.fixture(params=[FullRebalancePlanner, lambda: ThresholdRebalancePlanner(0)])
def planner(request) -> FullRebalancePlanner:
    return request.param()


def test_rebalance_sells_five_a_to_fund_ten_b(planner: FullRebalancePlanner) -> None:
    # Equity 1000: A is worth 600 and B 400; target values are 500 each.
    context = make_context()

    assert planner.get_intents(context) == [intent("A", Side.SELL, 5), intent("B", Side.BUY, 10)]
    assert context.snapshot == PortfolioSnapshot(0, 1000, {"A": 30, "B": 40})
    assert context.target.weights == {"A": 0.5, "B": 0.5}
    assert context.prices == {"A": 20.0, "B": 10.0}


def test_buys_use_total_equity_and_leave_unallocated_cash(planner: FullRebalancePlanner) -> None:
    context = make_context(cash=800, positions={"A": 10}, weights={"A": 0.5, "B": 0.25})

    assert planner.get_intents(context) == [intent("A", Side.BUY, 15), intent("B", Side.BUY, 25)]


@pytest.mark.parametrize("weights", [{"B": 1.0}, {"A": 0.0, "B": 1.0}])
def test_omitted_and_explicit_zero_targets_liquidate_holdings(planner, weights) -> None:
    assert planner.get_intents(make_context(weights=weights)) == [
        intent("A", Side.SELL, 30), intent("B", Side.BUY, 60),
    ]


def test_empty_target_sells_all_holdings(planner: FullRebalancePlanner) -> None:
    assert planner.get_intents(make_context(weights={})) == [
        intent("A", Side.SELL, 30), intent("B", Side.SELL, 40),
    ]


def test_rounding_targets_down_can_reduce_a_fractionally_overweight_holding(planner) -> None:
    # Equity 110: A target 55 / 20 = 2.75 shares; B target 55 / 10 = 5.5.
    context = make_context(cash=10, positions={"A": 3, "B": 4})

    assert planner.get_intents(context) == [intent("A", Side.SELL, 1), intent("B", Side.BUY, 1)]


@pytest.mark.parametrize("context", [
    make_context(positions={"A": 25, "B": 50}),
    make_context(cash=5, positions={}),  # Neither target can buy one share.
    make_context(positions={}),
    make_context(cash=1000, positions={}, weights={}),
])
def test_no_intents_when_no_whole_share_adjustment_is_needed(planner, context) -> None:
    assert planner.get_intents(context) == []


def test_sells_precede_buys_regardless_of_symbol_order(planner) -> None:
    context = make_context(positions={"B": 60, "A": 20})

    assert planner.get_intents(context) == [intent("B", Side.SELL, 10), intent("A", Side.BUY, 5)]


def test_planner_uses_execution_prices_and_preserves_decision_timestamp(planner) -> None:
    context = replace(make_context(cash=1000, positions={}), prices={"A": 100.0, "B": 50.0})

    assert planner.get_intents(context) == [intent("A", Side.BUY, 5), intent("B", Side.BUY, 10)]


def test_sizing_overrides_are_copied_and_default_to_up_to() -> None:
    sizing = {"A": SizingMode.FIXED}
    planner = FullRebalancePlanner(sizing)
    sizing["A"] = SizingMode.ALL_IN

    assert planner.get_intents(make_context(cash=1000, positions={})) == [
        intent("A", Side.BUY, 25, SizingMode.FIXED), intent("B", Side.BUY, 50),
    ]


@pytest.mark.parametrize("mode", [SizingMode.ALL_IN, SizingMode.PERCENT, None, "fixed"])
def test_rejects_sizing_modes_that_do_not_express_quantity_differences(mode) -> None:
    with pytest.raises(ValueError, match="UP_TO or FIXED"):
        FullRebalancePlanner({"A": mode})


@pytest.mark.parametrize("threshold, expected", [(0.124, True), (0.125, False), (0.126, False)])
def test_threshold_uses_strict_absolute_weight_drift(threshold: float, expected: bool) -> None:
    # Equity 800: A has weight .625, exactly .125 above target .5.
    context = make_context(positions={"A": 25, "B": 30})

    intents = ThresholdRebalancePlanner(threshold).get_intents(context)

    assert intents == ([intent("A", Side.SELL, 5), intent("B", Side.BUY, 10)] if expected else [])


def test_one_threshold_breach_rebalances_entire_portfolio() -> None:
    context = make_context(cash=100, positions={"A": 35, "B": 20}, weights={"A": 0.5, "B": 0.25})

    assert ThresholdRebalancePlanner(0.1).get_intents(context) == [
        intent("A", Side.SELL, 10), intent("B", Side.BUY, 5),
    ]


def test_decimal_threshold_equality_does_not_trigger_from_float_rounding() -> None:
    # Weights .55 and .45 are exactly five percentage points from .5.
    context = make_context(positions={"A": 55, "B": 90})

    assert ThresholdRebalancePlanner(0.05).get_intents(context) == []


def test_omitted_holding_can_trigger_threshold_rebalance() -> None:
    context = make_context(weights={"B": 0.5})

    assert ThresholdRebalancePlanner(0.5).get_intents(context) == [
        intent("A", Side.SELL, 30), intent("B", Side.BUY, 10),
    ]


def test_threshold_applies_to_initial_cash_portfolio() -> None:
    context = make_context(cash=1000, positions={})

    assert ThresholdRebalancePlanner(0.1).get_intents(context) == [
        intent("A", Side.BUY, 25), intent("B", Side.BUY, 50),
    ]
    assert ThresholdRebalancePlanner(0.5).get_intents(context) == []


def test_cash_drift_alone_does_not_trigger_rebalance() -> None:
    context = make_context(cash=200, positions={"A": 20, "B": 40})

    assert ThresholdRebalancePlanner(0.15).get_intents(context) == []


@pytest.mark.parametrize("threshold", [-0.01, 1.01, float("nan"), float("inf"), True, "0.1"])
def test_rejects_invalid_threshold(threshold) -> None:
    with pytest.raises(ValueError, match="threshold"):
        ThresholdRebalancePlanner(threshold)


@pytest.mark.parametrize("prices", [{"A": 20.0}, {"B": 10.0}])
def test_requires_prices_for_both_omitted_holdings_and_targets(planner, prices) -> None:
    context = replace(make_context(weights={"B": 1.0}), prices=prices)

    with pytest.raises(ValueError, match="Missing execution price"):
        planner.get_intents(context)


@pytest.mark.parametrize("price", [0, -1, float("nan"), float("inf"), True, "20"])
def test_rejects_invalid_execution_prices(planner, price) -> None:
    context = replace(make_context(), prices={"A": price, "B": 10.0})

    with pytest.raises(ValueError, match="Execution price for A"):
        planner.get_intents(context)


@pytest.mark.parametrize("snapshot, message", [
    (PortfolioSnapshot(0, -1, {}), "Portfolio value"),
    (PortfolioSnapshot(0, float("nan"), {}), "Portfolio value"),
    (PortfolioSnapshot(0, float("inf"), {}), "Portfolio value"),
    (PortfolioSnapshot(-1, 100, {}), "Cash"),
    (PortfolioSnapshot(float("nan"), 100, {}), "Cash"),
    (PortfolioSnapshot(101, 100, {}), "Cash"),
    (PortfolioSnapshot(0, 100, {"A": -1}), "Position quantity"),
    (PortfolioSnapshot(0, 100, {"A": 1.5}), "Position quantity"),
    (PortfolioSnapshot(0, 100, {"A": True}), "Position quantity"),
])
def test_rejects_invalid_snapshot(planner, snapshot, message) -> None:
    with pytest.raises(ValueError, match=message):
        planner.get_intents(replace(make_context(), snapshot=snapshot))


def test_rejects_execution_before_decision(planner) -> None:
    context = replace(make_context(), decision_timestamp=EXECUTION_TIME, execution_timestamp=DECISION_TIME)

    with pytest.raises(ValueError, match="cannot precede"):
        planner.get_intents(context)


def test_threshold_validates_inputs_even_when_it_would_skip_trading() -> None:
    with pytest.raises(ValueError, match="Missing execution price"):
        ThresholdRebalancePlanner(1).get_intents(replace(make_context(), prices={}))
