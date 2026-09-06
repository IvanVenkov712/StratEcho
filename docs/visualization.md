# Visualization

Strat Echo provides a Matplotlib API for inspecting a completed
`BacktestResult`. Visualization is intentionally separate from the backtest
engine: chart code consumes recorded results and cannot influence strategy
signals, executions, or portfolio accounting.

The `backtest` command can save the dashboard without opening an interactive
window:

```powershell
python -m backtester.cli backtest --chart reports/backtest-dashboard.png
```

The Python API can also create, customize, and export figures directly after
calling `BacktestEngine.run()`.

## Create the dashboard

Given an already configured `BacktestEngine` named `engine`, pass its completed
result to `create_backtest_figure()`:

```python
from matplotlib import pyplot as plt

from backtester.visualization.dashboard import create_backtest_figure

result = engine.run()
figure = create_backtest_figure(result, title="BuyAndHoldStrategy — AAPL")

# Display interactively.
plt.show()
plt.close(figure)
```

The function returns a `matplotlib.figure.Figure`. It does not display, save,
or close the figure. The caller owns those operations. Closing figures after
use is particularly important when generating many charts in a script or test.

To create and save the standard dashboard without opening a window, use
`export_backtest_dashboard()`:

```python
from backtester.visualization.export import export_backtest_dashboard

output_path = export_backtest_dashboard(
    result,
    "reports/backtest-dashboard.png",
    title="BuyAndHoldStrategy — AAPL",
    dpi=150,
)
```

The image format is inferred from the output file extension. Missing parent
directories are created automatically. Existing files are protected by
default; pass `overwrite=True` to replace one intentionally. The exporter owns
the figure it creates and always closes it, including when saving fails.

Use `create_backtest_figure()` directly when the figure must be displayed or
customized before saving. In that case, the caller continues to own displaying,
saving, and closing the figure.

## Dashboard panels

The CLI adds the configured strategy description and symbol as the dashboard's
figure-level title. Python callers can provide their own optional `title` to
either function.

The dashboard contains four vertically stacked panels with a shared time axis:

| Panel | Contents | Units |
| --- | --- | --- |
| Price | Candle closes, BUY/SELL signals, and BUY/SELL trade fills | Price units |
| Portfolio | Total equity, uninvested cash, and invested market value | Cash units |
| Position | Quantity held for `BacktestResult.symbol` | Whole shares |
| Risk | Drawdown from the running portfolio-equity peak | Percentage |

![Four-panel Strat Echo dashboard showing SPY prices and signal and trade markers, portfolio equity, cash and market value, position quantity, and drawdown](images/backtest-dashboard.png)

*Example dashboard for a 20/50-period simple moving-average crossover on SPY. The price panel shows when signals were generated and trades were filled. Reading downward, the remaining panels show how those trades affected portfolio equity and its cash and market-value components, the number of shares held, and the decline from the running equity peak. Results are illustrative.*

Every panel includes a title and legend. The common time axis keeps the same
timestamp horizontally aligned across all panels. Date labels are rotated for
readability, and the figure layout is adjusted before it is returned.

### Signals versus trades

The price panel deliberately distinguishes decisions from executions:

- hollow markers show strategy signals at the signal candle's timestamp and
  closing price;
- filled markers show successful trades at their fill timestamp and fill
  price;
- upward triangles represent BUY and downward triangles represent SELL.

Under the engine's normal timing model, a signal calculated from candle `T`'s
close becomes known at that close, while a resulting trade executes at candle
`T+1`'s open. The two markers can therefore have different timestamps and
prices. Rejected orders do not appear as trade markers because they do not
produce entries in `BacktestResult.trades`.

### Portfolio and drawdown definitions

Total equity is `BacktestRecord.snapshot.value`. Cash is
`BacktestRecord.snapshot.cash`, and market value is calculated as:

```text
market value = total equity - cash
```

Drawdown at each observation is:

```text
drawdown = portfolio value / running portfolio peak - 1
```

A zero running peak produces drawdown `0.0`, because a percentage decline from
zero cannot be measured. The risk axis displays fractional values as
percentages, so `-0.05` is shown as `-5%`.

## Compose a custom figure

The helpers in `backtester.visualization.charts` add one line or marker layer
to a caller-owned Matplotlib `Axes`. This supports smaller or differently
arranged figures without changing the standard dashboard:

```python
from matplotlib import pyplot as plt

from backtester.visualization.charts import plot_drawdown, plot_equity

figure, (equity_axes, risk_axes) = plt.subplots(2, 1, sharex=True)
plot_equity(equity_axes, result)
plot_drawdown(risk_axes, result)

equity_axes.set_title("Portfolio equity")
equity_axes.legend()
risk_axes.set_title("Drawdown")
risk_axes.legend()
figure.tight_layout()
```

Chart helpers add data and labels but leave titles, axes labels, grids,
legends, and figure lifecycle management to the caller. The lower-level
functions in `backtester.visualization.series` return timestamp and value lists
when non-Matplotlib consumers need the same data.

## Compare a strategy and benchmark

```powershell
python -m backtester.cli compare --strategy donchian-breakout --benchmark buy-and-hold --chart reports/comparison-dashboard.png
```

The comparison dashboard has five panels sharing one date axis:

| Panel | Contents | Units |
| --- | --- | --- |
| Portfolio equity (largest) | Strategy and benchmark total equity | Cash units |
| Drawdown | Each portfolio's decline from its own running equity peak | Percentage |
| Equity difference | Strategy equity minus benchmark equity, with a zero line | Cash units |
| Cash | Each portfolio's uninvested cash | Cash units |
| Position quantity | Each portfolio's quantity held in the common symbol | Whole shares |

Strategy lines are blue and solid; benchmark lines are orange and dashed.
Positive equity differences are shaded green and negative differences red.
Cash and quantity use recorded end-of-period observations, as do the existing
single-backtest panels. The figure includes both strategy descriptions, the
symbol, actual observation dates, and both sizing policies. The CLI appends a
table of already calculated metrics, using the same formatting as console output.

The benchmark uses all-in/all-out sizing, while the strategy uses the selected
sizing policy. Both runs use the same starting capital, candles, commission,
slippage, and cash-buffer settings. Equity includes simulated costs and is not
normalized; the difference is an amount of money, not a return percentage.

The Python API accepts two completed results:

```python
from backtester.visualization.comparison import create_comparison_figure
from backtester.visualization.export import export_comparison_dashboard

figure = create_comparison_figure(
    strategy_result,
    benchmark_result,
    strategy_name="Donchian Breakout",
    benchmark_name="Buy and Hold",
    subtitle="Strategy sizing: fixed shares\nBenchmark sizing: all in / all out",
)
# The caller owns displaying and closing this figure.
plt.close(figure)

export_comparison_dashboard(
    strategy_result,
    benchmark_result,
    "reports/comparison-dashboard.png",
    strategy_name="Donchian Breakout",
    benchmark_name="Buy and Hold",
)
```

Both functions accept optional `metric_rows`: a sequence of preformatted
`(metric_label, strategy_value, benchmark_value)` strings. Omitting it leaves
out the table; visualization does not recalculate performance metrics.

Comparison requires equal symbols and initial cash, identical timestamps, and
strictly increasing observations. Unequal lengths, missing dates, duplicate
dates, and unordered dates raise `ValueError`; no rows are filled or silently
aligned. Two empty results produce five empty panels.

The exporter shares the single-backtest export rules: file extension required,
positive DPI, parent directories created, existing files protected unless
`overwrite=True`, and the figure closed even when saving fails. TOML chart
paths are independent: `[compare].chart` controls comparison output and does
not inherit `[backtest].chart`. An explicit `--chart` overrides the applicable
configuration value.

## Empty results and limitations

An empty `BacktestResult` produces the same four labeled panels with empty
series; creating the dashboard does not fail.

Current limitations are:

- the single-backtest dashboard visualizes one result and one symbol;
- comparisons support two results for the same symbol and initial capital;
- price rendering uses closing-price lines rather than OHLC candlesticks;
- volume is not plotted;
- rejected order attempts are not plotted;
- the CLI saves charts but does not display them interactively.

## Test coverage

- [`test_visualization_series.py`](../tests/test_visualization_series.py)
  verifies the values and timestamps extracted from backtest records.
- [`test_visualization_charts.py`](../tests/test_visualization_charts.py)
  verifies individual line and marker layers.
- [`test_visualization_dashboard.py`](../tests/test_visualization_dashboard.py)
  verifies panel assembly, legends, percentage formatting, shared time limits,
  series routing, layout calls, and empty results.
- [`test_visualization_export.py`](../tests/test_visualization_export.py)
  verifies file-path validation, parent-directory creation, overwrite
    protection, save options, and figure cleanup.
- [`test_visualization_comparison.py`](../tests/test_visualization_comparison.py)
  verifies comparison panels, styles, metadata, table content, and empty results.

Return to the [project README](../README.md), see
[Backtesting assumptions](../README.md#backtesting-assumptions), or review the
[Performance metrics](metrics.md) definitions.
