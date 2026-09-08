# Market data

Strat Echo obtains historical OHLCV candles from Yahoo Finance or CSV files.
Both sources are converted to the same internal `Candle` representation before
a backtest starts, so the engine does not depend directly on either source.

## Yahoo Finance

`YFinanceDataSource` downloads daily (`1d`) data through the `yfinance`
package. OHLC prices are requested with automatic adjustment
(`auto_adjust=True`). Yahoo's adjusted close factor is applied consistently to
open, high, low, and close, so dividends and stock splits do not appear as
ordinary price discontinuities. The requested start date is inclusive and the
end date is exclusive.

```powershell
python -m backtester.cli backtest --source yfinance --symbol SPY --start 2024-01-01 --end 2025-01-01
```

Downloaded column names are normalized before the data passes through the same
validation as CSV input.

Adjusted Yahoo prices implicitly represent distributions as if they were
reinvested. Strat Echo does not separately credit dividend cash or update
share quantities for corporate actions. Consequently, Yahoo trade and
valuation prices are synthetic adjusted prices rather than the literal prices
quoted on each historical date. Explicit dividend cash flows must not be added
on top of this data because that would count distributions twice.

CSV OHLCV values are used as supplied. Strat Echo does not infer whether a CSV
contains adjusted or unadjusted prices, so one file should use a consistent
price convention throughout.

## CSV files

Use `--source csv` together with `--csv-path`. The path may identify one file
or a directory. When given a directory, Strat Echo looks for
`<SYMBOL>.csv`; for example, the symbol `SPY` maps to `SPY.csv`.

A CSV file must contain one timestamp column named `date`, `timestamp`, or
`datetime`, plus all five OHLCV columns:

| Column | Required | Meaning |
| --- | --- | --- |
| `date`, `timestamp`, or `datetime` | One of these | Candle timestamp in a format understood by pandas |
| `open` | Yes | Opening price |
| `high` | Yes | Highest price |
| `low` | Yes | Lowest price |
| `close` | Yes | Closing price |
| `volume` | Yes | Traded volume |
| `symbol` | No | Allows one file to contain multiple symbols; matching rows are selected |

Column names are converted to lowercase and spaces are replaced with
underscores. If a `symbol` column is present, symbol matching is case-sensitive.

Example CSV:

```csv
date,symbol,open,high,low,close,volume
2024-01-02,SPY,472.16,473.67,470.49,472.65,12345678
2024-01-03,SPY,470.43,471.19,468.17,468.79,14567890
```

Example command:

```powershell
python -m backtester.cli backtest --source csv --csv-path data/SPY.csv --symbol SPY --start 2024-01-01 --end 2025-01-01
```

When neither `--start` nor `--end` is supplied, `--csv-period-anchor` selects
one of three behaviors. Its default, `start-csv`, begins at the first CSV candle
for the selected symbol and ends `--years` calendar years later. `end-today`
ends the period today, while `end-csv` includes the selected symbol's final CSV
candle. Both end-anchored modes start `--years` calendar years before their
exclusive end boundary. Explicit date boundaries follow the common resolution
rules documented in the [CLI reference](cli.md#common-options).

## Combining assets into market frames

Use `market_frames_from_candles` to combine already loaded candle sequences
into the chronological `MarketFrame` sequence accepted by the multi-asset engine:

```python
from backtester.data.frames import market_frames_from_candles

frames = market_frames_from_candles({"AAPL": aapl_candles, "MSFT": msft_candles})
```

Every symbol must have the same strictly increasing timestamp sequence. The
function raises `ValueError` for duplicate or unordered timestamps, missing
bars, extra bars, or different timestamps, including different start/end dates.
It does not sort, fill, or discard bars to force alignment. Each frame retains
the original candle for every supplied symbol.

Dates absent from all assets, such as shared market holidays, are allowed;
the function does not infer a trading calendar or expected bar frequency.
Timezone-aware timestamps compare by instant; naive and aware timestamps cannot
be mixed. An empty mapping or all-empty sequences returns `[]`; an empty series
alongside a non-empty series is rejected. Different asset calendars require
separate execution and valuation rules and are not supported here.

## Validation and normalization

Before data reaches the engine, Strat Echo requires:

- timestamps sorted in ascending order with no duplicates;
- numeric, finite, and non-missing OHLCV values;
- strictly positive `open`, `high`, `low`, and `close` prices;
- non-negative volume;
- `high` greater than or equal to `low`;
- `open` and `close` between `low` and `high`.

Rows outside the requested date range are removed. Strat Echo does not sort
rows, fill missing values, remove duplicate timestamps, resample candles, or
otherwise repair invalid market data automatically. Invalid input fails with a
clear error so that changes to financial data remain explicit.

The CLI requires at least two candles after symbol and date filtering because
its standard metric report needs more than one portfolio observation.

CSV timestamps are not restricted to daily frequency and may be irregular.
However, metrics whose current names include “daily,” plus annual volatility
and annual Sharpe ratio, treat each consecutive candle as one period and use a
fixed 252-period annualization factor. Do not interpret those values as daily
or annual statistics for intraday or irregular CSV data. See
[Performance metrics](metrics.md) for the exact convention.

See the [CLI reference](cli.md) for all source and date options, or return to the [project README](../README.md).
