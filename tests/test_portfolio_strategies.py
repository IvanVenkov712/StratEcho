from datetime import datetime, timedelta

import pytest

from backtester.domain.market import Candle, MarketFrame
from backtester.domain.trading import PortfolioSnapshot, RebalanceDecision, TargetAllocation
from backtester.strategies.portfolio_strategies.simple_portfolio_strategies import (
    EqualWeightStrategy,
    PresetWeightStrategy,
)


TIMESTAMP = datetime(2026, 1, 1)


@pytest.mark.parametrize("count", [1, 2, 3, 9, 20])
def test_equal_weight_allocates_across_the_configured_universe(count: int) -> None:
    symbols = frozenset(f"ASSET{i}" for i in range(count))
    strategy = EqualWeightStrategy(symbols)

    decision = strategy.on_frame(MarketFrame(TIMESTAMP, {}), PortfolioSnapshot(1000, 1000, {}))

    assert isinstance(decision, RebalanceDecision)
    assert decision.timestamp == TIMESTAMP
    assert decision.target.weights == pytest.approx(dict.fromkeys(symbols, 1 / count))
    assert sum(decision.target.weights.values()) == pytest.approx(1)


def test_equal_weight_rejects_empty_universe_at_construction() -> None:
    with pytest.raises(ValueError, match="empty"):
        EqualWeightStrategy(frozenset())


@pytest.mark.parametrize("weights", [{}, {"A": 0.0}, {"A": 1.0}, {"A": 0.25, "B": 0.5}])
def test_preset_weight_preserves_targets_including_cash_remainder(weights: dict[str, float]) -> None:
    strategy = PresetWeightStrategy(weights)

    decision = strategy.on_frame(MarketFrame(TIMESTAMP, {}), PortfolioSnapshot(1000, 1000, {}))

    assert decision == RebalanceDecision(TIMESTAMP, TargetAllocation(weights))


@pytest.mark.parametrize("weights", [
    {"A": -0.1}, {"A": 1.1}, {"A": float("nan")},
    {"A": float("inf")}, {"A": -float("inf")}, {"A": 0.6, "B": 0.5},
])
def test_preset_weight_rejects_invalid_weights(weights: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="[Ww]eights"):
        PresetWeightStrategy(weights)


def test_preset_weight_copies_input_mapping() -> None:
    weights = {"A": 0.25, "B": 0.5}
    strategy = PresetWeightStrategy(weights)
    weights.clear()

    decision = strategy.on_frame(MarketFrame(TIMESTAMP, {}), PortfolioSnapshot(1000, 1000, {}))

    assert decision.target.weights == {"A": 0.25, "B": 0.5}


@pytest.mark.parametrize("strategy", [
    EqualWeightStrategy(frozenset({"A", "B"})),
    PresetWeightStrategy({"A": 0.5, "B": 0.5}),
])
def test_strategies_repeat_targets_with_current_timestamp_and_leave_snapshot_unchanged(strategy) -> None:
    snapshot = PortfolioSnapshot(100, 1000, {"A": 9})
    decisions = []
    for day, price in enumerate([100, 200]):
        timestamp = TIMESTAMP + timedelta(days=day)
        frame = MarketFrame(timestamp, {"A": Candle(timestamp, price, price, price, price, 10)})
        decisions.append(strategy.on_frame(frame, snapshot))

    assert decisions == [
        RebalanceDecision(TIMESTAMP + timedelta(days=day), TargetAllocation({"A": 0.5, "B": 0.5}))
        for day in range(2)
    ]
    assert snapshot == PortfolioSnapshot(100, 1000, {"A": 9})
    with pytest.raises(TypeError):
        decisions[0].target.weights["A"] = 1.0
