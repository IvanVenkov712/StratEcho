# Portfolio strategies and rebalancing

The Python API supports two constant-target portfolio strategies:

- `EqualWeightStrategy(frozenset({"A", "B"}))` requests 50% in each asset.
  Its universe must be non-empty.
- `PresetWeightStrategy({"A": 0.5, "B": 0.25})` requests those exact weights,
  leaving 25% for cash. Weights must be in `[0, 1]` and sum to at most one.
  An empty mapping requests all cash.

Both return a `RebalanceDecision` timestamped with the observed frame on every
call to `on_frame`. Targets are independent of current prices and holdings.
The engine validates target symbols against the market universe and executes
the previous frame's decision at the next frame's open. The final decision
cannot execute without a subsequent frame.

## Planners

`FullRebalancePlanner` calculates each desired whole-share holding from one
pre-trade opening snapshot:

```text
target_quantity = floor(opening_equity * target_weight / opening_price)
quantity_difference = target_quantity - current_quantity
```

Positive differences produce buys; negative differences produce sells. Zero
differences produce no intent. Holdings omitted from the target are sold in
full. Rounding can leave additional cash. For example, equity of 1,000 with
30 A shares at 20 and 40 B shares at 10 has current values of 600 and 400.
A 50/50 target produces a sale of 5 A and a purchase of 10 B, before costs.

`ThresholdRebalancePlanner(threshold=0.05)` uses the same calculation only
when **any asset's absolute weight drift is strictly greater than five
percentage points**. Drift within `1e-12` of the threshold counts as equality
to avoid trades caused by floating-point rounding. Once triggered, it plans the whole portfolio, including
assets below the threshold. Omitted holdings have zero target weight. Cash
has no independent drift trigger. The threshold applies to initial investment
too: a target at or below the threshold may remain in cash. Zero equity
produces no threshold-triggered trades.

```python
from backtester.execution.decision_execution.rebalance_decision_executor import RebalanceDecisionExecutor
from backtester.rebalance.simple_rebalance_planners import FullRebalancePlanner, ThresholdRebalancePlanner
from backtester.strategies.portfolio_strategies.simple_portfolio_strategies import PresetWeightStrategy

strategy = PresetWeightStrategy({"A": 0.5, "B": 0.25})
planner = ThresholdRebalancePlanner(threshold=0.05)
# Alternatively: planner = FullRebalancePlanner()
# Supply your configured IntentExecutor (resolver, broker and priority):
decision_executor = RebalanceDecisionExecutor(planner, intent_executor)
```

These components are available through the Python API; there are no CLI
selectors for them yet.

## Sizing and costs

Planned quantities exclude commissions and slippage. By default, each intent
uses `SizingMode.UP_TO` with the absolute quantity difference as its limit.
The existing resolver can reduce purchases to fit actual cash, allocation-gap
budgets and costs. `FullRebalancePlanner({"A": SizingMode.FIXED})` instead
requires the full difference for A; an unaffordable fixed buy can be skipped.
The threshold planner also accepts this optional `sizing` mapping. Other sizing
modes are rejected because they do not express a target quantity difference.

The planner returns sells before buys, with symbols sorted within each side.
`IntentExecutor` applies its configured priority within each side and refreshes
the portfolio before resolving each order. Earlier fills and costs can thus
reduce later buys; exact final weights are not guaranteed. The planner does
not redistribute residual cash or retry skipped quantities within the same
rebalance. Every intent retains the original decision timestamp.

The snapshot must be valued using the supplied execution prices. Missing or
non-positive prices, non-finite cash/equity, negative or fractional positions,
and execution times preceding the decision fail clearly.

Tests use deterministic quantities in
[`test_rebalance_planners.py`](../tests/test_rebalance_planners.py) and cover
the strategy contracts in
[`test_portfolio_strategies.py`](../tests/test_portfolio_strategies.py).
