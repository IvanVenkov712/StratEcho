# Known issues and follow-up work

This file contains actionable work that is intentionally deferred. Verification
results and completed review notes belong in pull requests or commit messages,
not in this backlog.

## Financial and statistical correctness

- [ ] Make candle frequency explicit for volatility and Sharpe calculations.
  CSV input currently permits intraday and irregular observations, while annual
  volatility and annual Sharpe ratio always assume 252 periods per year. Either
  restrict these metrics to daily candles or make `periods_per_year`
  configurable.
- [ ] Prevent annualized-return overflow for extreme growth over very short
  elapsed intervals. Prefer a log-space calculation with an explicit infinity
  or `N/A` policy.
## Engine and public API

- [ ] Define reporting for fixed buys that exceed the allocation-gap budget.
  The quantity resolver currently returns -1, so no order or broker rejection
  is recorded. Distinguish allocation-budget limits from insufficient portfolio
  cash when deciding how skipped intents should appear in results.
- [ ] Validate that `Strategy.on_candle()` returns a `Signal`; invalid values
  must fail clearly instead of being treated like `HOLD`.
- [ ] Define ownership of stateful backtest dependencies. Either require a fresh
  strategy and broker portfolio for every engine, or reset their state before
  each run.
- [ ] Convert sequences stored in frozen `BacktestResult` instances to tuples
  and make `PortfolioSnapshot.positions` immutable so results are deeply
  immutable.
- [ ] Validate fixed commissions as finite, non-negative numbers at model
  construction time.
- [ ] Apply complete integer, range, and relationship validation to strategy
  parameters at the CLI boundary instead of relying partly on constructors.
- [ ] Add explicit signal-to-execution linkage to `BacktestRecord` if result
  auditing or visualization requires it.

## Architecture cleanup

- [ ] Remove or migrate the unused sizing implementation in
  `src/backtester/sizing/position_sizing.py`; the engine uses sizing
  instructions and quantity resolvers.
- [ ] Remove superseded strategy code: `_MovingAverageCrossStrategy`,
  `_MeanReversionStrategy`, and the commented RSI implementation.
- [ ] Decide whether empty placeholders such as `strategies/breakout.py` and the
  `reporting` package should be implemented or removed.
- [ ] Review currently unused concepts, including `SizingMode.UP_TO`,
  `ResolutionContext.portfolio_value`, and
  `ExecutionCostCalculator.estimate_sell_cost()`.

## Tooling and utilities

- [ ] Refactor `data_download.py` behind functions and a `main` guard. Accept
  symbols, dates, and output paths explicitly instead of downloading and
  overwriting tracked files when the module is imported.
- [ ] Make local development tooling match CI by including the lint dependency
  in the development extra or documenting a separate lint extra.
- [ ] Decide whether style violations and a minimum coverage percentage should
  become blocking CI checks.
