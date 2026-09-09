"""CLI universe validation, configuration precedence, and engine wiring."""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, call

import pandas as pd
import pytest
import matplotlib

matplotlib.use("Agg")

from backtester.cli import commands, factories
from backtester.cli.app import main
from backtester.cli.arguments import parse_args
from backtester.config import ConfigError, load_config
from backtester.data.loader import CSVDataSource
from backtester.domain.market import Candle, MarketFrame
from backtester.domain.trading import Signal, SizingMode


@pytest.mark.parametrize("command", ["backtest", "compare"])
@pytest.mark.parametrize(
    ("options", "symbols"),
    [([], ("SPY",)), (["--symbol", " spy "], ("SPY",)),
     (["--symbols", "spy", "qqq"], ("SPY", "QQQ")),
     (["--symbol", "sizing"], ("SIZING",))],
)
def test_symbol_forms_normalize_to_one_universe(command, options, symbols):
    args = parse_args([command, *options])
    assert args.symbols == symbols
    assert args.allocations == {symbol: 1 / len(symbols) for symbol in symbols}
    assert args.priorities == dict.fromkeys(symbols, 0)


@pytest.mark.parametrize("count", [3, 7, 9, 11, 21, 100])
def test_equal_weights_fit_the_engine_sum_limit(count):
    args = parse_args(["--symbols", *(f"S{index}" for index in range(count))])
    assert sum(args.allocations.values()) <= 1
    assert list(args.allocations.values()) == pytest.approx([1 / count] * count)


def test_explicit_weights_and_partial_priorities_are_normalized():
    args = parse_args([
        "--symbols", "SPY", "QQQ", "--allocation", "spy=0.6",
        "--allocation=qqq=0.3", "--priority", "qqq=-2",
    ])
    assert args.allocations == {"SPY": 0.6, "QQQ": 0.3}
    assert args.priorities == {"SPY": 0, "QQQ": -2}


@pytest.mark.parametrize("options", [
    ["--symbol", "SPY", "--symbols", "QQQ"],
    ["--symbols"], ["--symbol", " "], ["--symbols", "SPY", "spy"],
    ["--symbols", "SPY", "bad symbol"],
    ["--symbols", "SPY", "QQQ", "--allocation", "SPY=0.5"],
    ["--allocation", "QQQ=1"], ["--priority", "QQQ=1"],
    ["--allocation", "SPY=0.5", "--allocation", "spy=0.5"],
    ["--priority", "SPY=1", "--priority", "spy=2"],
    ["--allocation", "SPY"], ["--allocation", "SPY="],
    ["--allocation", "=1"], ["--allocation", "SPY=oops"],
    ["--allocation", "SPY=nan"], ["--allocation", "SPY=inf"],
    ["--allocation", "SPY=-0.1"], ["--allocation", "SPY=1.1"],
    ["--symbols", "SPY", "QQQ", "--allocation", "SPY=0.6", "--allocation", "QQQ=0.6"],
    ["--priority", "SPY"], ["--priority", "SPY=1.5"],
    ["--siz", "fixed", "--buy-size", "1", "--sell-size", "1"],
])
def test_invalid_universe_settings_fail_at_parse_time(options):
    with pytest.raises(SystemExit) as exc:
        parse_args(options)
    assert exc.value.code == 2


def write_config(tmp_path: Path, contents: str) -> Path:
    path = tmp_path / "universe.toml"
    path.write_text(contents, encoding="utf-8")
    return path


def test_cli_collections_replace_toml_and_sizing_flags_apply_to_every_symbol(tmp_path):
    path = write_config(tmp_path, '''
[backtest]
symbols = ["SPY", "QQQ"]
allocations = { SPY = 0.6, QQQ = 0.3 }
priorities = { SPY = -1, QQQ = 2 }
sizing = "percent"
buy_percent = 0.5
sell_percent = 1.0
[backtest.sizing_by_symbol.QQQ]
sizing = "fixed"
buy_size = 2
sell_size = 1
''')
    configured = parse_args(["--config", str(path)])
    assert configured.sizing_by_symbol["SPY"].sizing == "percent"
    assert configured.sizing_by_symbol["QQQ"].buy_size == 2
    args = parse_args([
        "--config", str(path), "--allocation", "SPY=0.4", "--allocation", "QQQ=0.6",
        "--priority", "QQQ=-3", "--sizing=fixed", "--buy-size=4", "--sell-size", "3",
    ])
    assert args.allocations == {"SPY": 0.4, "QQQ": 0.6}
    assert args.priorities == {"SPY": 0, "QQQ": -3}
    for settings in args.sizing_by_symbol.values():
        assert (settings.sizing, settings.buy_size, settings.sell_size) == ("fixed", 4, 3)
        assert settings.buy_percent is None
    with pytest.raises(SystemExit):
        parse_args(["--config", str(path), "--allocation", "SPY=1"])


@pytest.mark.parametrize(
    ("contents", "cli", "expected"),
    [('[backtest]\nsymbol = "AAPL"', ["--symbols", "SPY", "QQQ"], ("SPY", "QQQ")),
     ('[backtest]\nsymbols = ["SPY", "QQQ"]', ["--symbol=MSFT"], ("MSFT",))],
)
def test_cli_universe_replaces_either_toml_symbol_form(tmp_path, contents, cli, expected):
    path = write_config(tmp_path, contents)
    assert parse_args(["--config", str(path), *cli]).symbols == expected


def test_per_symbol_sizing_inherits_values_and_cli_parameters_override_it(tmp_path):
    path = write_config(tmp_path, '''
[backtest]
symbols = ["SPY", "QQQ"]
sizing = "fixed"
buy_size = 2
sell_size = 3
[backtest.sizing_by_symbol.qqq]
buy_size = 7
''')
    args = parse_args(["--config", str(path), "--sell-size", "5"])
    plan = factories.create_multi_asset_sizing_plan(args)
    assert plan.plans["SPY"].buy.value == 2
    assert plan.plans["QQQ"].buy.value == 7
    assert all(item.sell.value == 5 for item in plan.plans.values())
    benchmark = factories.create_multi_asset_sizing_plan(args, benchmark=True)
    assert all(item.buy.mode == SizingMode.ALL_IN for item in benchmark.plans.values())


@pytest.mark.parametrize("contents", [
    '[backtest]\nsymbols = []', '[backtest]\nsymbols = "SPY"',
    '[backtest]\nsymbols = [1]', '[backtest]\nsymbol = "SPY"\nsymbols = ["SPY"]',
    '[backtest]\nallocations = {}', '[backtest]\nallocations = []',
    '[backtest]\nallocations = { SPY = true }', '[backtest]\npriorities = { SPY = 1.5 }',
    '[backtest]\npriorities = { SPY = true }', '[backtest.sizing_by_symbol.SPY]\nbuy_size = "1"',
    '[backtest.sizing_by_symbol.SPY]\nbuffer_rate = 0.1',
])
def test_toml_universe_schema_rejects_invalid_types_and_keys(tmp_path, contents):
    with pytest.raises(ConfigError):
        load_config(write_config(tmp_path, contents), required=True)


@pytest.mark.parametrize("contents", [
    '[backtest]\nallocations = { SPY = 0.5, spy = 0.5 }',
    '[backtest]\npriorities = { QQQ = 1 }',
    '[backtest.sizing_by_symbol.QQQ]\nsizing = "fixed"',
    '[backtest.sizing_by_symbol.SPY]\nsizing = "fixed"',
    '[backtest.sizing_by_symbol.SPY]\nbuy_percent = 0.5',
])
def test_toml_symbol_settings_use_cli_semantic_validation(tmp_path, contents):
    with pytest.raises(SystemExit):
        parse_args(["--config", str(write_config(tmp_path, contents))])


def test_strategy_factory_creates_independent_instances_with_shared_parameters(monkeypatch):
    strategies = [Mock(on_candle=Mock(return_value=Signal.BUY)), Mock(on_candle=Mock(return_value=Signal.HOLD))]
    constructor = Mock(side_effect=strategies)
    monkeypatch.setattr(factories, "SimpleMovingAverageCrossStrategy", constructor)
    args = parse_args(["--symbols", "SPY", "QQQ", "--short-window", "2", "--long-window", "3"])
    strategy = factories.create_multi_asset_strategy(args.strategy, args)
    candle = Candle(datetime(2024, 1, 1), 10, 10, 10, 10, 100)
    signal = strategy.on_frame(MarketFrame(candle.timestamp, {"SPY": candle, "QQQ": candle}))
    assert signal.signals == {"SPY": Signal.BUY, "QQQ": Signal.HOLD}
    assert constructor.call_args_list == [call(short_window_size=2, long_window_size=3)] * 2
    for instance in strategies:
        instance.on_candle.assert_called_once_with(candle)


def prices(symbol: str) -> pd.DataFrame:
    opening, closing = (10, 11) if symbol == "SPY" else (20, 18)
    return pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "open": [opening, opening], "high": [opening, max(opening, closing)],
        "low": [opening, min(opening, closing)], "close": [opening, closing],
        "volume": [100, 100],
    })


@pytest.mark.parametrize("command", ["backtest", "compare"])
@pytest.mark.parametrize("priority, order", [(None, ["QQQ", "SPY"]), ("SPY=-1", ["SPY", "QQQ"])])
def test_commands_load_each_symbol_once_and_wire_allocations_and_priority(
    command, priority, order, monkeypatch, tmp_path, capsys,
):
    source = Mock(load=Mock(side_effect=lambda symbol, start, end: prices(symbol)))
    monkeypatch.setattr(factories, "create_data_source", Mock(return_value=source))
    exporter = Mock(return_value=tmp_path / "chart.png")
    monkeypatch.setattr(commands, "export_backtest_dashboard", exporter)
    monkeypatch.setattr(commands, "export_comparison_dashboard", exporter)
    options = [
        command, "--symbols", "SPY", "QQQ", "--allocation", "SPY=0.6", "--allocation", "QQQ=0.3",
        "--strategy", "buy-and-hold", "--initial-capital", "1000",
        "--start", "2024-01-01", "--end", "2024-01-03", "--chart", str(tmp_path / "chart.png"),
    ]
    if priority:
        options.extend(["--priority", priority])
    assert main(options) == 0
    assert source.load.call_args_list == [
        call("SPY", "2024-01-01", "2024-01-03"), call("QQQ", "2024-01-01", "2024-01-03"),
    ]
    result = exporter.call_args.args[0]
    assert [trade.symbol for trade in result.trades] == order
    assert result.records[-1].snapshot.positions == {"SPY": 60, "QQQ": 15}
    assert result.records[-1].snapshot.cash == 100
    assert result.records[-1].snapshot.value == 1030
    assert all(trade.timestamp == datetime(2024, 1, 2) for trade in result.trades)
    if command == "compare":
        benchmark = exporter.call_args.args[1]
        assert benchmark is not result
        assert benchmark.allocation == result.allocation
        assert benchmark.records[-1].snapshot.value == 1030
        assert len(benchmark.trades) == 2
    output = capsys.readouterr().out
    assert "Assets: SPY, QQQ" in output
    assert "Allocations: SPY=60.00%, QQQ=30.00%" in output
    assert f"within each side: {', '.join(order)}" in output


def test_commands_reject_misaligned_symbol_data(monkeypatch, capsys):
    spy, qqq = prices("SPY"), prices("QQQ")
    qqq.loc[1, "date"] = pd.Timestamp("2024-01-03")
    source = Mock(load=Mock(side_effect=[spy, qqq]))
    monkeypatch.setattr(factories, "create_data_source", Mock(return_value=source))
    assert main(["--symbols", "SPY", "QQQ", "--start", "2024-01-01", "--end", "2024-01-04"]) == 1
    assert "Timestamps for 'QQQ' must match 'SPY'" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["backtest", "compare"])
@pytest.mark.parametrize("directory", [False, True])
def test_multi_symbol_csv_and_real_chart_export(command, directory, tmp_path, capsys):
    if directory:
        csv_path = tmp_path / "data"
        csv_path.mkdir()
        for symbol in ("SPY", "QQQ"):
            prices(symbol).to_csv(csv_path / f"{symbol}.csv", index=False)
    else:
        csv_path = tmp_path / "prices.csv"
        pd.concat([prices(symbol).assign(symbol=symbol) for symbol in ("SPY", "QQQ")]).to_csv(csv_path, index=False)
    chart_path = tmp_path / "chart.png"
    assert main([
        command, "--symbols", "SPY", "QQQ", "--source", "csv", "--csv-path", str(csv_path),
        "--strategy", "buy-and-hold", "--chart", str(chart_path),
    ]) == 0
    assert chart_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert "2024-01-01 (inclusive)" in capsys.readouterr().out


def test_multi_symbol_csv_requires_symbol_column(tmp_path, capsys):
    csv_path = tmp_path / "prices.csv"
    prices("SPY").to_csv(csv_path, index=False)
    assert main(["--symbols", "SPY", "QQQ", "--source", "csv", "--csv-path", str(csv_path)]) == 1
    assert "must contain a symbol column" in capsys.readouterr().err


@pytest.mark.parametrize("anchor, expected", [
    ("start-csv", ("2024-01-01", "2025-01-01")),
    ("end-csv", ("2023-02-04", "2024-02-04")),
])
def test_csv_anchor_uses_universe_bounds_without_intersecting_dates(anchor, expected):
    source = Mock(spec=CSVDataSource)
    source.first_available_date.side_effect = [datetime(2024, 1, 5).date(), datetime(2024, 1, 1).date()]
    source.last_available_date.side_effect = [datetime(2024, 2, 1).date(), datetime(2024, 2, 3).date()]
    args = parse_args([
        "--symbols", "SPY", "QQQ", "--source", "csv", "--csv-path", "data",
        "--csv-period-anchor", anchor, "--years", "1",
    ])
    assert commands._resolve_command_date_range(args, source) == expected


def test_compare_reports_and_executes_individual_toml_sizing(tmp_path, monkeypatch, capsys):
    path = write_config(tmp_path, '''
[backtest]
symbols = ["SPY", "QQQ"]
initial_capital = 1000
strategy = "buy-and-hold"
sizing = "fixed"
buy_size = 1
sell_size = 1
[backtest.sizing_by_symbol.QQQ]
buy_size = 2
''')
    source = Mock(load=Mock(side_effect=lambda symbol, start, end: prices(symbol)))
    monkeypatch.setattr(factories, "create_data_source", Mock(return_value=source))
    exporter = Mock(return_value=tmp_path / "chart.png")
    monkeypatch.setattr(commands, "export_comparison_dashboard", exporter)
    assert main(["compare", "--config", str(path), "--chart", str(tmp_path / "chart.png")]) == 0
    result, benchmark, _ = exporter.call_args.args
    assert result.records[-1].snapshot.positions == {"SPY": 1, "QQQ": 2}
    assert result.records[-1].snapshot.value == 997
    assert benchmark.records[-1].snapshot.positions == {"SPY": 50, "QQQ": 25}
    assert benchmark.records[-1].snapshot.value == 1000
    output = capsys.readouterr().out
    assert "SPY: fixed shares (buy=1, sell=1); QQQ: fixed shares (buy=2, sell=1)" in output


def test_cli_universe_change_rejects_stale_toml_allocations(tmp_path):
    path = write_config(tmp_path, '[backtest]\nsymbol = "SPY"\nallocations = { SPY = 1.0 }')
    with pytest.raises(SystemExit):
        parse_args(["--config", str(path), "--symbol", "QQQ"])
