# Strat Echo

Strat Echo is a Python backtesting project for experimenting with simple
trading strategies on historical OHLCV market data. It is designed to show how
a backtesting engine, strategies, portfolio accounting, trade execution, and
performance metrics fit together without hiding the core logic inside a large
external framework.

It is an educational project, not a live trading bot, and does not provide
investment advice.

## Features

Strat Echo can:

- load historical candle data from Yahoo Finance or CSV files;
- validate and normalize OHLCV data before running a backtest;
- generate buy, sell, or hold signals from several strategies;
- execute generated orders on the next candle's open;
- model adverse slippage and zero, fixed, or proportional commissions;
- use all-in/all-out, fixed-share, or percentage-based position sizing with an optional cash buffer;
- track cash, positions, trades, orders, and portfolio value;
- calculate return, volatility, Sharpe ratio, drawdown, and trade metrics;
- compare a strategy against a benchmark on the same market data;
- visualize prices, signals, fills, portfolio state, positions, and drawdown;
- configure CLI runs from TOML with explicit CLI-over-file precedence.

## Installation

Strat Echo requires Python 3.12 or later. Install it from the repository root
in editable mode:

```powershell
python -m pip install -e .
```

This installs the package and its runtime dependencies (`pandas`,
`typing-extensions`, `yfinance`, and `matplotlib`). Editable mode makes changes
under `src` available without reinstalling the package.

For development, install the optional test dependencies as well:

```powershell
python -m pip install -e ".[dev]"
```

## Quick start

Run the default moving-average crossover strategy on five years of daily SPY
data:

```powershell
python -m backtester.cli backtest
```

Compare a strategy with buy and hold:

```powershell
python -m backtester.cli compare --strategy simple-moving-average --benchmark buy-and-hold --symbol SPY
```

Comparison output shows every common metric in three value columns: the
strategy result, the benchmark result, and the difference calculated as
`strategy - benchmark`.

Use a local CSV file instead of Yahoo Finance:

```powershell
python -m backtester.cli backtest --source csv --csv-path data/SPY.csv --symbol SPY --start 2024-01-01 --end 2025-01-01
```

Include a 0.1% proportional commission and 0.05% slippage:

```powershell
python -m backtester.cli backtest --commission-model proportional --commission-rate 0.001 --slippage-rate 0.0005
```

Use a TOML configuration file:

```powershell
python -m backtester.cli backtest --config strat-echo.example.toml
```

If `--config` is omitted, the CLI automatically uses `strat-echo.toml` from
the current working directory when that file exists. Settings follow
`CLI option > TOML option > application default`, so individual file values
can be overridden for one run. See the
[`strat-echo.example.toml`](strat-echo.example.toml) file and the
[TOML configuration reference](docs/configuration.md) for the schema,
validation rules, and path behavior.

See the [CLI reference](docs/cli.md) for all commands, options, and output
examples.

## Strategies

The CLI provides buy-and-hold, simple and exponential moving-average
crossovers, three RSI conventions, simple and exponential mean-reversion, and
Donchian breakout strategies. The default is a simple moving-average crossover
with 20- and 50-period windows.

See the dedicated [Strategy reference](docs/strategies.md) for every tested
strategy, its formulas, parameters, signal boundaries, warm-up period, CLI
name and aliases, examples, reset behavior, test coverage, and the shared
next-candle-open execution timing.

## Position sizing

Position sizing converts a signal into a whole-share order quantity.

| CLI name | Behavior |
| --- | --- |
| `all-in-all-out` | Buys the maximum affordable whole shares and sells the entire position. |
| `fixed` | Uses explicit buy and sell share quantities. |
| `percent` | Uses a fraction of available cash for buys and a fraction of owned shares for sells. |

All-in/all-out is the default. Percentage sizing does not target a
percentage of total portfolio equity. Because the engine supports only whole
shares, a valid sizing decision can produce a quantity of zero.

The optional `--buffer-rate` limits buy quantities so that the configured
fraction of current cash remains unspent, while sell quantities still follow
the selected policy. For example, `--buffer-rate 0.05` reserves 5% of cash.
When configured, `BufferQuantityResolver` wraps the base `QuantityResolver`.
Both use the same `BuyQuantityCapper`, which includes configured commission
and adverse slippage when checking how many shares fit within the budget.

## Visualization

The Python API can turn a completed `BacktestResult` into a four-panel
Matplotlib dashboard containing prices with signals and fills, portfolio
equity/cash/market value, position quantity, and drawdown. The `backtest`
command can save this dashboard directly:

```powershell
python -m backtester.cli backtest --chart reports/backtest-dashboard.png
```

<p align="center">
  <img src="docs/images/backtest-dashboard.png" alt="Strat Echo dashboard showing SPY prices and signal and trade markers, portfolio equity, cash and market value, position quantity, and drawdown" width="700">
</p>

<p align="center"><em>Example output for a 20/50-period simple moving-average crossover on SPY. Hollow markers show strategy signals, while filled markers show the resulting trades; the lower panels track portfolio composition, position size, and drawdown. Results are illustrative.</em></p>

The path can also be stored as `chart = "reports/backtest-dashboard.png"`
under `[backtest]` in the TOML configuration.

The `compare` command saves five panels comparing portfolio equity, drawdown,
equity difference, cash, and position quantity, followed by a metrics table:

```powershell
python -m backtester.cli compare --chart reports/comparison-dashboard.png
```

Set `chart` under `[compare]` to configure this path separately from backtests.
Both sizing policies appear in the subtitle; the benchmark uses all-in/all-out
sizing. Strategy lines are blue and solid; benchmark lines are orange and dashed.

Given an already configured `BacktestEngine` named `engine`:

```python
from matplotlib import pyplot as plt

from backtester.visualization.dashboard import create_backtest_figure

result = engine.run()
figure = create_backtest_figure(result, title="BuyAndHoldStrategy - AAPL")
plt.show()
plt.close(figure)
```

To save the standard dashboard directly, including automatic figure cleanup:

```python
from backtester.visualization.export import export_backtest_dashboard

export_backtest_dashboard(
    result,
    "reports/backtest-dashboard.png",
    title="BuyAndHoldStrategy - AAPL",
)
```

See [Visualization](docs/visualization.md) for panel definitions, marker timing,
saving and overwrite behavior, composable chart helpers, ownership,
limitations, and tests.

## Backtesting assumptions

The engine separates signal generation from execution to avoid look-ahead
bias:

1. The strategy receives candle `T` only after all earlier candles have been
   processed; no future candle is supplied.
2. A signal generated from candle `T`'s close creates an order intent without a
   quantity.
3. At candle `T+1` open, the position size is calculated using the current
   portfolio and the opening price supplied by the selected data source.
4. Slippage adjusts the fill price against the trader: BUY fills move up and
   SELL fills move down.
5. Commission is calculated from the resulting fill and deducted from cash.
6. Portfolio value is recorded at each candle's close.

An executable order preserves both points in the lifecycle:
`signal_timestamp` identifies candle `T`, when the signal became known, while
`submitted_timestamp` identifies candle `T+1`, when the intent was sized and
submitted for execution. A successful trade's timestamp records its fill time.

A signal from the final candle remains unexecuted because the data contains no
`T+1` open. See the [Strategy reference](docs/strategies.md) for each
strategy's warm-up and signal rules under this timing model.

### Backtest results

`BacktestEngine.run()` returns a cached `BacktestResult` containing the traded
symbol, the cash captured when the engine was created, chronological
per-candle records, successful trades produced by that run, and every attempted
order execution, including rejections.

Each `BacktestRecord` retains the original `Candle`, the signal generated from
that candle, and an end-of-candle `PortfolioSnapshot`. The snapshot separates
cash, position quantities, and total portfolio value. It is valued with the
current candle's close after any pending order has executed at that candle's
open. `BacktestRecord.market_value` is the value of all open positions and is
calculated as total portfolio value minus cash.

Trade history belongs to the result rather than the broker. Only successful
executions create entries in `result.trades`; rejected attempts remain in
`result.order_executions` with no trade.

The broker is long-only. Overnight price gaps affect all-in and percentage
order quantities because sizing happens at the execution open. Fixed-size
orders can be rejected when cash or shares are insufficient.

Yahoo Finance candles use adjusted OHLC prices. Dividends and stock splits are
therefore embedded in the price series, with distributions implicitly treated
as reinvested instead of being credited to portfolio cash. CSV prices are used
as supplied; callers are responsible for choosing a consistent adjusted or
unadjusted convention. See [Market data](docs/data.md) for the consequences of
these conventions.

The default is zero slippage with no commission. A fixed commission is charged
once per executed trade. A proportional commission is a fraction of trade
notional (`quantity * fill price`). Rates use decimal fractions, so `0.001`
means `0.1%`.

All-in and percentage BUY quantities are resolved against a budget that
already includes the configured commission and adverse slippage. Fixed BUY
instructions remain exact and can be rejected when unaffordable unless a
`--buffer-rate` is supplied; with a buffer, fixed quantities are capped to the
affordable amount. A rejected order remains visible in the backtest result, but
it does not create a trade or change the portfolio. The CLI displays
individual rejection details with the concise reason `Insufficient funds` or
`Insufficient position` when there are at most 10 rejected orders; above that
limit, it displays the rejection count without listing every order.

## Documentation

- [TOML configuration](docs/configuration.md): precedence, paths, complete file
  structure, supported keys, and validation
- [CLI reference](docs/cli.md): commands, parameters, sizing, and execution-cost
  options
- [Strategy reference](docs/strategies.md): tested strategies, formulas,
  signals, warm-up behavior, parameters, and CLI examples
- [Market data](docs/data.md): Yahoo Finance behavior, CSV format, and validation
- [Performance metrics](docs/metrics.md): formulas, interpretations, and edge cases
- [Visualization](docs/visualization.md): dashboard panels, signal and fill
  timing, figure output, composition, limitations, and tests

## Running tests

Run the test suite from the repository root:

```powershell
pytest
```
