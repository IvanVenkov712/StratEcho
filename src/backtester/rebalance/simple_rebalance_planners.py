"""Whole-share rebalancing from execution-time prices and a single snapshot."""

from collections.abc import Mapping
from math import floor, isclose, isfinite
from numbers import Real

from backtester.domain.trading import OrderIntent, Side, SizingInstruction, SizingMode
from backtester.rebalance.rebalance_planner import RebalanceContext, RebalancePlanner


class FullRebalancePlanner(RebalancePlanner):
    """Move each holding toward floor(opening equity * target weight / price).

    Omitted holdings have a zero target. Rounding leaves residual cash. Targets
    exclude costs; the existing resolver caps UP_TO buys for available cash,
    allocation budgets, commissions and slippage. FIXED overrides request the
    entire difference and may be skipped if unaffordable. ALL_IN and PERCENT
    are unsupported because they do not express a target quantity difference.
    """

    def __init__(self, sizing: Mapping[str, SizingMode] | None = None) -> None:
        modes = dict(sizing) if sizing is not None else {}
        if any(mode not in (SizingMode.UP_TO, SizingMode.FIXED) for mode in modes.values()):
            raise ValueError("Rebalance sizing must be UP_TO or FIXED")
        super().__init__(modes)

    def get_intents(self, context: RebalanceContext) -> list[OrderIntent]:
        """Return quantity differences, sells first, retaining decision time."""
        symbols = sorted(set(context.target.weights) | set(context.snapshot.positions))
        _validate_context(context, symbols)
        if not self._should_rebalance(context, symbols):
            return []

        sells = []
        buys = []
        for symbol in symbols:
            weight = context.target.weights.get(symbol, 0.0)
            target_quantity = floor(context.snapshot.value * weight / context.prices[symbol])
            difference = target_quantity - context.snapshot.positions.get(symbol, 0)
            if difference == 0:
                continue
            side = Side.BUY if difference > 0 else Side.SELL
            intent = OrderIntent(
                symbol, side, context.decision_timestamp,
                SizingInstruction(abs(difference), self._sizing.get(symbol, SizingMode.UP_TO)),
            )
            (buys if side == Side.BUY else sells).append(intent)
        return sells + buys

    def _should_rebalance(self, context: RebalanceContext, symbols: list[str]) -> bool:
        return True


class ThresholdRebalancePlanner(FullRebalancePlanner):
    """Rebalance all assets if any absolute asset-weight drift exceeds a limit.

    A threshold of 0.05 means five percentage points, not 5% of the target
    weight. Equality within 1e-12 does not trigger trading. Cash has no separate drift
    trigger. An omitted holding still participates with a zero target weight.
    """

    def __init__(self, threshold: float, sizing: Mapping[str, SizingMode] | None = None) -> None:
        if not _is_finite_number(threshold) or not 0 <= threshold <= 1:
            raise ValueError("threshold must be a finite number in [0, 1]")
        super().__init__(sizing)
        self._threshold = threshold

    def _should_rebalance(self, context: RebalanceContext, symbols: list[str]) -> bool:
        if context.snapshot.value == 0:
            return False
        for symbol in symbols:
            drift = abs(
                context.snapshot.positions.get(symbol, 0) * context.prices[symbol] / context.snapshot.value
                - context.target.weights.get(symbol, 0.0)
            )
            # Decimal weights can land just above an equal threshold in floats.
            if drift > self._threshold and not isclose(drift, self._threshold, rel_tol=0, abs_tol=1e-12):
                return True
        return False


def _is_finite_number(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and isfinite(value)


def _validate_context(context: RebalanceContext, symbols: list[str]) -> None:
    if context.execution_timestamp < context.decision_timestamp:
        raise ValueError("Execution timestamp cannot precede decision timestamp")
    if not _is_finite_number(context.snapshot.value) or context.snapshot.value < 0:
        raise ValueError("Portfolio value must be finite and non-negative")
    if not _is_finite_number(context.snapshot.cash) or not 0 <= context.snapshot.cash <= context.snapshot.value:
        raise ValueError("Cash must be finite and between zero and portfolio value")
    for symbol in symbols:
        if symbol not in context.prices:
            raise ValueError(f"Missing execution price for {symbol}")
        price = context.prices[symbol]
        if not _is_finite_number(price) or price <= 0:
            raise ValueError(f"Execution price for {symbol} must be finite and positive")
        quantity = context.snapshot.positions.get(symbol, 0)
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 0:
            raise ValueError(f"Position quantity for {symbol} must be a non-negative integer")
