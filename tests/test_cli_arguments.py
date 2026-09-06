from pathlib import Path

import pytest

from backtester.cli.arguments import (
    DEFAULT_COMMISSION_MODEL,
    DEFAULT_CONFIG_PATH,
    DEFAULT_CSV_PERIOD_ANCHOR,
    DEFAULT_ENTRY_WINDOW,
    DEFAULT_EXIT_WINDOW,
    DEFAULT_INITIAL_CAPITAL,
    DEFAULT_LONG_WINDOW,
    DEFAULT_SHORT_WINDOW,
    DEFAULT_SIZING,
    DEFAULT_SLIPPAGE_RATE,
    DEFAULT_SYMBOL,
    DEFAULT_YEARS,
    STRATEGY_CHOICES,
    parse_args,
)

def test_parse_args_uses_backtest_defaults_when_no_command_is_given() -> None:
    args = parse_args([])

    assert args.command == "backtest"
    assert args.config == DEFAULT_CONFIG_PATH
    assert args.symbol == DEFAULT_SYMBOL
    assert args.years == DEFAULT_YEARS
    assert args.source == "yfinance"
    assert args.csv_period_anchor == DEFAULT_CSV_PERIOD_ANCHOR
    assert args.initial_capital == DEFAULT_INITIAL_CAPITAL
    assert args.sizing == DEFAULT_SIZING
    assert args.buy_size is None
    assert args.sell_size is None
    assert args.buy_percent is None
    assert args.sell_percent is None
    assert args.buffer_rate is None
    assert args.commission_model == DEFAULT_COMMISSION_MODEL
    assert args.fixed_commission is None
    assert args.commission_rate is None
    assert args.slippage_rate == DEFAULT_SLIPPAGE_RATE
    assert args.strategy == "moving-average"
    assert args.short_window == DEFAULT_SHORT_WINDOW
    assert args.long_window == DEFAULT_LONG_WINDOW
    assert args.entry_window == DEFAULT_ENTRY_WINDOW
    assert args.exit_window == DEFAULT_EXIT_WINDOW
    assert args.chart_path is None


def test_help_uses_strat_echo_program_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--help"])

    assert exc_info.value.code == 0
    assert "usage: strat-echo" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["backtest", "compare"])
def test_parse_args_accepts_chart_path(command: str) -> None:
    chart_path = Path("reports/backtest.png")

    args = parse_args([command, "--chart", str(chart_path)])

    assert args.chart_path == chart_path


def test_compare_chart_config_is_separate_and_cli_can_override(tmp_path: Path) -> None:
    config_path = tmp_path / "charts.toml"
    config_path.write_text(
        '[backtest]\nchart = "reports/backtest.png"\n'
        '[compare]\nchart = "reports/compare.png"\n',
        encoding="utf-8",
    )
    assert parse_args(["compare", "--config", str(config_path)]).chart_path == Path(
        "reports/compare.png"
    )
    assert parse_args(["backtest", "--config", str(config_path)]).chart_path == Path(
        "reports/backtest.png"
    )
    assert parse_args([
        "compare", "--config", str(config_path), "--chart", "reports/override.png",
    ]).chart_path == Path("reports/override.png")


@pytest.mark.parametrize("anchor", ["start-csv", "end-today", "end-csv"])
def test_parse_args_accepts_csv_period_anchor(anchor: str) -> None:
    args = parse_args(["--csv-period-anchor", anchor])

    assert args.csv_period_anchor == anchor


def test_cli_csv_period_anchor_overrides_toml(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        '[backtest]\ncsv_period_anchor = "start-csv"\n',
    )

    args = parse_args(
        [
            "--config",
            str(config_path),
            "--csv-period-anchor",
            "end-today",
        ]
    )

    assert args.csv_period_anchor == "end-today"


def test_parse_args_loads_explicit_toml_configuration(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        """
[backtest]
symbol = "AAPL"
years = 3
csv_period_anchor = "end-today"
initial_capital = 25000.0
chart = "reports/from-config.png"
sizing = "fixed"
buy_size = 4
sell_size = 2
buffer_rate = 0.1
commission_model = "fixed"
fixed_commission = 1.5
strategy = "rsi"
rsi_period = 10
rsi_min = 25.0
rsi_max = 75.0
""",
    )

    args = parse_args(["--config", str(config_path)])

    assert args.config == config_path
    assert args.symbol == "AAPL"
    assert args.years == 3
    assert args.csv_period_anchor == "end-today"
    assert args.initial_capital == 25_000
    assert args.chart_path == Path("reports/from-config.png")
    assert args.sizing == "fixed"
    assert args.buy_size == 4
    assert args.sell_size == 2
    assert args.buffer_rate == 0.1
    assert args.commission_model == "fixed"
    assert args.fixed_commission == 1.5
    assert args.strategy == "rsi"
    assert args.rsi_period == 10
    assert args.rsi_min == 25
    assert args.rsi_max == 75
    assert args.short_window == DEFAULT_SHORT_WINDOW


def test_cli_options_override_toml_and_toml_overrides_defaults(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
[backtest]
symbol = "AAPL"
years = 3
initial_capital = 25000.0
chart = "reports/from-config.png"
""",
    )

    args = parse_args(
        [
            "--config",
            str(config_path),
            "--symbol",
            "MSFT",
            "--years",
            "2",
            "--chart",
            "reports/from-cli.png",
        ]
    )

    assert args.symbol == "MSFT"  # CLI beats TOML.
    assert args.years == 2  # CLI beats TOML.
    assert args.initial_capital == 25_000  # TOML beats the code default.
    assert args.chart_path == Path("reports/from-cli.png")  # CLI beats TOML.
    assert args.strategy == "moving-average"  # No CLI/TOML value: code default.


def test_cli_selector_override_discards_dependent_values_for_old_toml_choice(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
[backtest]
sizing = "percent"
buy_percent = 0.5
sell_percent = 1.0
commission_model = "proportional"
commission_rate = 0.001
""",
    )

    args = parse_args(
        [
            "--config",
            str(config_path),
            "--sizing",
            "fixed",
            "--buy-size",
            "4",
            "--sell-size",
            "2",
            "--commission-model",
            "fixed",
            "--fixed-commission",
            "1.5",
        ]
    )

    assert args.sizing == "fixed"
    assert args.buy_size == 4
    assert args.sell_size == 2
    assert args.buy_percent is None
    assert args.sell_percent is None
    assert args.commission_model == "fixed"
    assert args.fixed_commission == 1.5
    assert args.commission_rate is None


def test_parse_args_loads_default_config_from_current_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_config(tmp_path, "[backtest]\nsymbol = 'AAPL'\n", "strat-echo.toml")
    monkeypatch.chdir(tmp_path)

    args = parse_args([])

    assert args.config == DEFAULT_CONFIG_PATH
    assert args.symbol == "AAPL"


def test_compare_uses_backtest_and_compare_config_sections(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        """
[backtest]
symbol = "MSFT"
strategy = "mean-reversion"

[compare]
benchmark = "rsi"
""",
    )

    args = parse_args(["compare", "--config", str(config_path)])

    assert args.command == "compare"
    assert args.symbol == "MSFT"
    assert args.strategy == "mean-reversion"
    assert args.benchmark == "rsi"


def test_config_option_may_precede_explicit_compare_command(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        "[backtest]\nsymbol = 'MSFT'\n[compare]\nbenchmark = 'rsi'\n",
    )

    args = parse_args(["--config", str(config_path), "compare"])

    assert args.command == "compare"
    assert args.symbol == "MSFT"
    assert args.benchmark == "rsi"


def test_parse_args_rejects_missing_explicit_config_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing_path = tmp_path / "missing.toml"

    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--config", str(missing_path)])

    assert exc_info.value.code == 2
    assert "Configuration file does not exist" in capsys.readouterr().err


def test_toml_values_use_the_same_argparse_validation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_config(tmp_path, "[backtest]\nyears = 0\n")

    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--config", str(config_path)])

    assert exc_info.value.code == 2
    assert "value must be a positive integer" in capsys.readouterr().err


def test_parse_args_accepts_backtest_options_without_explicit_command() -> None:
    csv_path = Path("prices.csv")

    args = parse_args(
        [
            "--source",
            "csv",
            "--csv-path",
            str(csv_path),
            "--symbol",
            "AAPL",
            "--strategy",
            "rsi",
            "--rsi-period",
            "10",
            "--rsi-min",
            "25",
            "--rsi-max",
            "75",
            "--initial-capital",
            "25000",
        ]
    )

    assert args.command == "backtest"
    assert args.source == "csv"
    assert args.csv_path == csv_path
    assert args.symbol == "AAPL"
    assert args.strategy == "rsi"
    assert args.rsi_period == 10
    assert args.rsi_min == 25
    assert args.rsi_max == 75
    assert args.initial_capital == 25_000


def test_parse_args_accepts_compare_command_and_benchmark() -> None:
    args = parse_args(
        [
            "compare",
            "--strategy",
            "mean-reversion",
            "--benchmark",
            "rsi",
        ]
    )

    assert args.command == "compare"
    assert args.strategy == "mean-reversion"
    assert args.benchmark == "rsi"


def test_parse_args_accepts_donchian_breakout_windows() -> None:
    args = parse_args(
        [
            "--strategy",
            "donchian-breakout",
            "--entry-window",
            "55",
            "--exit-window",
            "21",
        ]
    )

    assert args.strategy == "donchian-breakout"
    assert args.entry_window == 55
    assert args.exit_window == 21


def test_parse_args_loads_donchian_breakout_from_toml(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        """
[backtest]
strategy = "donchian-breakout"
entry_window = 55
exit_window = 21
""",
    )

    args = parse_args(["--config", str(config_path)])

    assert args.strategy == "donchian-breakout"
    assert args.entry_window == 55
    assert args.exit_window == 21


@pytest.mark.parametrize("strategy_name", STRATEGY_CHOICES)
def test_parse_args_accepts_every_strategy_as_strategy_and_benchmark(
    strategy_name: str,
) -> None:
    args = parse_args(
        [
            "compare",
            "--strategy",
            strategy_name,
            "--benchmark",
            strategy_name,
        ]
    )

    assert args.strategy == strategy_name
    assert args.benchmark == strategy_name


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (
            ["--sizing", "fixed", "--buy-size", "3"],
            "--buy-size and --sell-size are required when --sizing fixed is used",
        ),
        (
            ["--sizing", "percent", "--buy-percent", "0.5"],
            "--buy-percent and --sell-percent are required when --sizing percent is used",
        ),
        (
            ["--buy-size", "3"],
            "--buy-size and --sell-size may only be used with --sizing fixed",
        ),
        (
            ["--buy-percent", "0.5"],
            "--buy-percent and --sell-percent may only be used with --sizing percent",
        ),
    ],
)
def test_parse_args_rejects_incomplete_or_irrelevant_sizing_options(
    arguments: list[str],
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(arguments)

    assert exc_info.value.code == 2
    assert message in capsys.readouterr().err


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (
            ["--commission-model", "fixed"],
            "--fixed-commission is required when --commission-model fixed is used",
        ),
        (
            ["--fixed-commission", "2.50"],
            "--fixed-commission may only be used with --commission-model fixed",
        ),
        (
            ["--commission-model", "proportional"],
            "--commission-rate is required when --commission-model proportional is used",
        ),
        (
            ["--commission-rate", "0.001"],
            "--commission-rate may only be used with --commission-model proportional",
        ),
    ],
)
def test_parse_args_rejects_incomplete_or_irrelevant_commission_options(
    arguments: list[str],
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(arguments)

    assert exc_info.value.code == 2
    assert message in capsys.readouterr().err


@pytest.mark.parametrize("value", ["-0.01", "1.01", "nan", "inf"])
def test_parse_args_rejects_percentage_outside_zero_to_one(
    value: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(
            [
                "--sizing",
                "percent",
                "--buy-percent",
                value,
                "--sell-percent",
                "0.5",
            ]
        )

    assert exc_info.value.code == 2
    assert "value must be between 0 and 1" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["-0.01", "1", "nan", "inf"])
def test_parse_args_rejects_invalid_slippage_rate(
    value: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--slippage-rate", value])

    assert exc_info.value.code == 2
    assert "value must be between 0 (inclusive) and 1 (exclusive)" in (
        capsys.readouterr().err
    )


@pytest.mark.parametrize("value", ["-0.01", "1", "nan", "inf"])
def test_parse_args_rejects_invalid_buffer_rate(
    value: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--buffer-rate", value])

    assert exc_info.value.code == 2
    assert "value must be between 0 (inclusive) and 1 (exclusive)" in (
        capsys.readouterr().err
    )


@pytest.mark.parametrize("value", ["-0.01", "nan", "inf"])
def test_parse_args_rejects_invalid_fixed_commission(
    value: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(
            ["--commission-model", "fixed", "--fixed-commission", value]
        )

    assert exc_info.value.code == 2
    assert "value must be a non-negative finite number" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["backtest", "compare"])
def test_csv_source_requires_csv_path(
    command: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args([command, "--source", "csv"])

    assert exc_info.value.code == 2
    assert "--csv-path is required when --source csv is used" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("option", "value", "message"),
    [
        ("--years", "0", "value must be a positive integer"),
        ("--short-window", "-1", "value must be a positive integer"),
        ("--entry-window", "0", "value must be a positive integer"),
        ("--exit-window", "-1", "value must be a positive integer"),
        ("--initial-capital", "0", "value must be positive"),
    ],
)
def test_parse_args_rejects_non_positive_values(
    option: str,
    value: str,
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args([option, value])

    assert exc_info.value.code == 2
    assert message in capsys.readouterr().err


def _write_config(
    tmp_path: Path,
    contents: str,
    filename: str = "settings.toml",
) -> Path:
    path = tmp_path / filename
    path.write_text(contents.strip() + "\n", encoding="utf-8")
    return path
