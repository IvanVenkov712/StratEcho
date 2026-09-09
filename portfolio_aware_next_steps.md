I’d introduce **strategies that produce target portfolio weights**, with a separate component responsible for rebalancing. Your existing multi-asset engine provides much of the foundation. No code was modified.

**1. Separate allocation, scheduling, and execution**

These answer three different questions:

| Responsibility | Question | Example |
|---|---|---|
| Allocation strategy | What portfolio do we want? | 50% SPY, 30% QQQ, 20% cash |
| Rebalance policy | When should we move toward it? | Every 20 frames or when weights drift |
| Rebalance planner | What trades are needed? | Sell 3 SPY, buy 5 QQQ |

This lets Equal Weight and Risk Parity share the same scheduling and execution logic. It also distinguishes **recalculating weights** from **trading back to existing weights**: equal weights can remain constant while holdings drift every day.

Your current [AssetAllocation](src/backtester/sizing/asset_allocation.py) represents buy-sizing targets. It limits additional purchases but does not sell overweight positions. Changing those weights alone would therefore be insufficient.

**2. Add a distinct target-weight strategy interface**

Your current `MultiAssetStrategy.on_frame()` returns per-symbol BUY/SELL/HOLD signals. Those signals cannot directly express “reduce this position from 40% to 25%.”

I’d initially keep that interface and introduce a sibling `AllocationStrategy`, rather than making every existing strategy support two output formats.

The proposed concepts would be:

| Concept | Purpose |
|---|---|
| `AllocationStrategy` | Observe chronological market frames and calculate desired weights |
| `TargetAllocation` | Immutable, timestamped weights covering the entire supported universe |
| `RebalancePolicy` | Decide whether a rebalance is due |
| `RebalancePlanner` | Convert targets and current holdings into orders |

For `TargetAllocation`, I’d start with long-only weights, no leverage, and a total at most 1. The remainder represents cash. Require every supported symbol explicitly; a zero weight means liquidate that holding.

Also distinguish **no new target** from **a target of all cash**.

“Portfolio-aware” does not necessarily mean each allocation formula needs holdings. Equal Weight and basic Markowitz depend on market inputs; the planner needs holdings. When a strategy eventually considers turnover or existing exposure, give it a detached, read-only portfolio snapshot—not the mutable portfolio or broker.

A unified strategy decision type could come later if both strategy families need shared composition. The separate interface is easier to introduce and understand now.

**3. Preserve your timing model**

Your [BacktestEngine](src/backtester/engine/backtest.py) already executes decisions from frame T at frame T+1’s open. Preserve that sequence:

1. Execute previously queued decisions at the current open.
2. Observe the completed current frame and update historical estimates.
3. If rebalancing is due and enough history exists, calculate and queue target weights.
4. Record the closing portfolio state.

At the next open, resolve those **already-decided weights** into quantities using opening prices. Do not recalculate expected returns or covariance using that next frame.

This retains your existing assumption that quantities can be resolved using opening prices and filled at that open, with configured slippage. Document it as a simulation convention.

For the first schedule, “every N frames after initial allocation” is straightforward. Monthly scheduling needs an exact definition: for example, decide at the first observed close of a new month and execute at the following open. Avoid detecting month-end by peeking at the next dataset row.

**4. Plan the whole rebalance together**

Your current resolver handles intents individually and refreshes equity after each fill. For rebalancing, I’d calculate desired holdings from **one pre-trade opening snapshot**, then execute sells before buys.

Ignoring costs temporarily:

\[
q_i^{target}=\left\lfloor\frac{w_i E}{P_i}\right\rfloor,
\qquad
\Delta q_i=q_i^{target}-q_i^{current}
\]

Here, \(E\) is opening equity and \(P_i\) is the asset’s opening price.

For example:

| Asset | Current value | Target weight | Desired change |
|---|---:|---:|---:|
| A | 600 | 50% | Sell 100 |
| B | 400 | 50% | Buy 100 |

At prices A = 20 and B = 10, this means selling 5 A and buying 10 B, assuming zero costs.

With commissions and slippage, the proceeds may not fund all 10 B. Reuse your existing execution-cost calculator and affordability capper, cap purchases against actual available cash, and record the resulting deviation from target.

For the first version:

- Freeze desired quantities for that rebalance.
- Sell before buying.
- Use deterministic buy priority when cash is insufficient.
- Leave residual cash from whole-share rounding.
- Record skipped or reduced orders.
- Retry remaining deviations only when the policy next triggers.

This is understandable and testable. Proportional distribution of scarce cash can follow later.

The planner should use its own target-difference sizing; routing through the current percent/all-in sizing rules would change the meaning of the target.

**5. Introduce the allocation methods incrementally**

| Method | Inputs | Rule |
|---|---|---|
| Equal Weight | Asset universe | \(w_i=1/N\) |
| Inverse Volatility | Trailing returns | Weights proportional to \(1/\sigma_i\) |
| Minimum Variance | Covariance matrix | Minimize \(w^\top\Sigma w\) |
| Equal Risk Contribution | Covariance matrix | Equalize each asset’s contribution to portfolio risk |
| Markowitz mean–variance | Expected returns and covariance | Balance expected return against variance |

For Equal Risk Contribution, normalized contributions satisfy:

\[
\frac{w_i(\Sigma w)_i}{w^\top\Sigma w}=\frac1N
\]

Inverse volatility is a useful intermediate implementation, but it is not generally equivalent to equal risk contribution because correlations matter. [MOSEK risk-budgeting reference](https://docs.mosek.com/portfolio-cookbook/risk_parity.html)

“Markowitz” needs a specific objective. One option is maximizing:

\[
\mu^\top w-\frac{\lambda}{2}w^\top\Sigma w
\]

subject to long-only, fully invested constraints. Another is minimizing variance for a required expected return. I’d implement minimum variance first because it avoids choosing an expected-return estimator initially. [MOSEK mean–variance reference](https://docs.mosek.com/portfolio-cookbook/markowitz.html)

For estimation, explicitly define trailing simple returns, lookback length, covariance convention, and consistent time units. A window of 60 returns requires 61 prices. Preserve your strict timestamp alignment; do not silently fill missing observations.

Until enough history exists, remain in cash. Invalid estimates or optimizer failures should produce a clear diagnostic rather than silently switching strategies.

**6. Update results and comparisons alongside the engine**

Your [BacktestResult](src/backtester/engine/backtest_result.py) currently stores one static allocation. Dynamic strategies need target history as well as actual holdings.

I’d record decision timestamps, requested weights, rebalance reasons, and execution outcomes. Useful plots would show target versus actual weights, cash weight, and transaction costs.

There is also a concrete comparison constraint in your open [comparison.py](src/backtester/visualization/comparison.py): `_validate_results()` requires identical allocations. That would block meaningful Equal Weight versus Markowitz comparisons. Portfolio comparisons should instead check compatible universes, evaluation dates, and initial capital, with consistent cost assumptions. Use a common evaluation start after sufficient warm-up.

**My suggested implementation order:** fixed target weights with scheduled rebalancing → Equal Weight → drift thresholds → inverse volatility → minimum variance → Equal Risk Contribution → full Markowitz.

Start with deterministic tests for overweight sales, underweight purchases, next-open timing, fees, rounding, all-cash targets, and insufficient history. That first fixed-weight rebalance gives you the execution foundation on which all the allocation formulas can depend.