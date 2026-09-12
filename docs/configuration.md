# TOML configuration reference

Strat Echo can read every `backtest` and `compare` setting from a TOML file.
The command-line interface remains available for one-off overrides.

## Value priority

Effective values are selected independently with this priority:

1. an option written on the command line;
2. the corresponding option in the TOML file;
3. the default defined by the application.

For example, if `research.toml` selects `AAPL` and three years, this command
uses `MSFT` from the CLI, three years from TOML, and the default initial
capital:

```powershell
python -m backtester.cli backtest --config research.toml --symbol MSFT
```

## Configuration path

Pass a file explicitly with `--config`:

```powershell
python -m backtester.cli backtest --config configs/aapl.toml
python -m backtester.cli compare --config configs/aapl.toml
```

`--config` can also precede an explicit command:

```powershell
python -m backtester.cli --config configs/aapl.toml compare
```

When `--config` is omitted, Strat Echo looks for `strat-echo.toml` in the
current working directory. A missing default file is ignored and all values
fall back to normal application defaults. A missing explicitly named file is
an error; this prevents a misspelled explicit path from being silently
ignored.

Relative paths, including `csv_path` and `chart`, are interpreted from the
current working directory. They are not interpreted relative to the package
installation or to the custom configuration file.

The repository includes
[`strat-echo.example.toml`](../strat-echo.example.toml). Copy it to
`strat-echo.toml` to use it automatically, or pass it directly to `--config`.

## File structure

Configuration uses snake_case keys corresponding directly to kebab-case CLI
options. For example, `initial_capital` represents `--initial-capital` and
`short_window` represents `--short-window`.

```toml
[backtest]
symbol = "AAPL"
years = 3
source = "csv"
csv_path = "data/AAPL.csv"
csv_period_anchor = "start-csv"
initial_capital = 25000.0
chart = "reports/aapl-backtest.png"

sizing = "percent"
buy_percent = 0.5
sell_percent = 1.0
buffer_rate = 0.01

commission_model = "proportional"
commission_rate = 0.001
slippage_rate = 0.0005

strategy = "simple-moving-average"
short_window = 10
long_window = 40
entry_window = 20
exit_window = 10

[compare]
benchmark = "buy-and-hold"
```

### The `[backtest]` table

`[backtest]` contains the settings for a single backtest and the settings
shared by both commands, including the strategy under test. Consequently,
`compare` uses the same data, portfolio, execution, and strategy settings as
`backtest`. Position sizing applies to the strategy run; the benchmark always
uses all-in/all-out while retaining the configured cash buffer. The `chart`
setting is the other exception: it applies only to
`backtest`; comparison charts use `[compare].chart`.
Strategy parameters are shared between the strategy and benchmark; there are
no benchmark-specific window or threshold keys.

Supported keys are:

| Group | Keys |
| --- | --- |
| Data and period | `symbol` or `symbols`, `years`, `start`, `end`, `source`, `csv_path`, `csv_period_anchor` |
| Portfolio | `initial_capital`, `allocations`, `priorities` |
| Output | `chart` |
| Position sizing | `sizing`, `buy_size`, `sell_size`, `buy_percent`, `sell_percent`, `buffer_rate`, `sizing_by_symbol` |
| Execution costs | `commission_model`, `fixed_commission`, `commission_rate`, `slippage_rate` |
| Strategy selection | `strategy` |
| Moving average | `short_window`, `long_window` |
| RSI | `rsi_period`, `rsi_min`, `rsi_max` |
| Mean reversion | `mean_window`, `mean_threshold` |
| Donchian breakout | `entry_window`, `exit_window` |

All strategy parameter keys may coexist in one file. A run uses only the keys
relevant to its selected strategy; the others remain available for a later CLI
override.

### Strategy values

The `strategy` and `benchmark` values support:

- `buy-and-hold`;
- `simple-moving-average` and `exponential-moving-average`;
- `cutler-rsi`, `exponential-rsi`, and `wilder-rsi`;
- `simple-mean-reversion` and `exponential-mean-reversion`;
- `donchian-breakout`.

The original `moving-average`, `rsi`, and `mean-reversion` values remain
supported as aliases. See the [Strategy reference](strategies.md) for the exact
mapping, formulas, constraints, signal timing, and warm-up behavior.

### The `[compare]` table

`[compare]` contains `benchmark` and optional `chart`. It is applied by the `compare` command
and ignored by `backtest`.

### Multi-asset settings

```toml
[backtest]
symbols = ["SPY", "QQQ"]
source = "csv"
csv_path = "data" # SPY.csv and QQQ.csv; a combined file needs a symbol column
strategy = "simple-moving-average"
short_window = 10
long_window = 40
allocations = { SPY = 0.6, QQQ = 0.3 }
priorities = { QQQ = -1 } # SPY defaults to 0
sizing = "percent"
buy_percent = 0.5
sell_percent = 1.0

[backtest.sizing_by_symbol.QQQ]
sizing = "fixed"
buy_size = 2
sell_size = 2

[compare]
benchmark = "buy-and-hold"
```

`symbols` is a non-empty array of strings and cannot coexist with `symbol`.
Both forms are trimmed and uppercased. `allocations` and `priorities` are tables
keyed by symbol; nested tables such as `[backtest.allocations]` are equivalent
to the inline form above. Allocation values are finite numbers in `[0, 1]`,
totaling at most `1`, with a weight for every symbol. Entirely omitting the
table selects equal weights; an empty or partial table is an error.
Priorities are integers, including negative values, with unspecified symbols
defaulting to `0`. Unknown symbols and duplicates after normalization fail.

Each `[backtest.sizing_by_symbol.SYMBOL]` table may contain only `sizing`,
`buy_size`, `sell_size`, `buy_percent`, and `sell_percent`. Unspecified settings
inherit the global sizing values. Changing a symbol's sizing mode discards
inherited parameters for the previous mode. Each resulting plan must be valid.
`buffer_rate` remains a shared modifier and cannot be set per symbol.

Sizing precedence is **CLI flags > per-symbol TOML > global TOML > defaults**.
An explicit CLI sizing flag or parameter applies to every symbol. Changing the
mode discards the old mode's TOML parameters for each affected symbol. Strategies
and their parameters are shared, with distinct instances per symbol and run.
The benchmark always uses all-in/all-out regardless of per-symbol sizing.

An explicit `--symbol` or `--symbols` replaces either TOML universe form.
Other symbol-specific TOML settings are retained and validated against that
universe; stale entries cause an error. Supplying any CLI `--allocation`
replaces the entire TOML allocation table, so the CLI must supply every weight.
Supplying any CLI `--priority` replaces the TOML priority table, with omitted
symbols reverting to `0`. Collections are never partially merged or silently
rescaled. For example:

```powershell
strat-echo backtest --config multi.toml --allocation SPY=0.5 --allocation QQQ=0.5 --priority SPY=-2
strat-echo backtest --config multi.toml --sizing fixed --buy-size 4 --sell-size 4
```

See [CLI universe behavior](cli.md#symbols-allocations-and-priorities) for
allocation budgets, execution order, and strict data alignment.

## TOML value types

Strings and dates must be quoted. Integer settings such as `years` and
`short_window` must use TOML integers. Monetary values, rates, and thresholds
accept TOML integers or floating-point numbers.

Rates are decimal fractions. For example, `0.001` means `0.1%`, not `0.001%`.

`chart` is a quoted output path whose extension selects the image format. Its
parent directories are created automatically, and an existing file is not
overwritten. It is equivalent to passing `--chart PATH` to the corresponding command.

## Validation and related settings

The same semantic validation is applied regardless of where a value comes
from. Choices, positive-number constraints, rate ranges, and required related
settings are therefore identical for CLI and TOML. Unknown sections, unknown
keys, wrong TOML types, malformed TOML, and invalid combinations fail with a
clear error rather than being ignored.

Related settings must form a complete model. For example:

- `sizing = "fixed"` requires `buy_size` and `sell_size`;
- `sizing = "percent"` requires `buy_percent` and `sell_percent`;
- optional `buffer_rate` accepts `[0, 1)` and may be combined with any sizing policy;
- `commission_model = "fixed"` requires `fixed_commission`;
- `commission_model = "proportional"` requires `commission_rate`.

Strategy constructors also enforce family-specific relationships such as
`short_window < long_window`, `rsi_period > 1`, ordered RSI thresholds within
`[0, 100]`, a mean-reversion threshold within `[0, 1]`, and positive Donchian
entry and exit windows. These failures are reported by the CLI before a
backtest begins.

If a CLI option changes `sizing` or `commission_model`, TOML-only parameters
belonging to the old selection are discarded. Required parameters for the new
selection must be supplied by the CLI. This makes it possible to replace a
complete model without stale TOML settings causing a conflict:

```powershell
python -m backtester.cli backtest --config percent.toml --sizing fixed --buy-size 10 --sell-size 10
```

`buffer_rate` is independent of the base sizing selection. When present, it
caps buys to leave the configured fraction of each order's cash-limited
allocation gap unspent, while sells are unchanged. For example,
`buffer_rate = 0.05` leaves 5% of that buy budget unspent.
The CLI applies it by wrapping the base `QuantityResolver` in a
`BufferQuantityResolver`. Both resolvers share one `BuyQuantityCapper`, so buy
affordability uses the same commission and slippage models as the broker.

The shared affordability tolerance is fixed in code and has no TOML setting.
It is independent of `buffer_rate`; see
[Rounding and affordability](../README.md#rounding-and-affordability) for its
values and the treatment of cash remainders and whole-share quantities.

See the [CLI reference](cli.md) for all commands and options, or return to the
[project README](../README.md).
