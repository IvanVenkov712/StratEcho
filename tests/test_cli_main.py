from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest

from backtester.cli import commands, main
from backtester.cli.commands import resolve_date_range
from backtester.engine.backtest_result import BacktestResult

FIXTURES_DIR = Path(__file__).parent / "fixtures"

def test_resolve_date_range_handles_leap_day_when_subtracting_years() -> None:
    assert resolve_date_range(None, "2024-02-29", 1) == (
        "2023-02-28",
        "2024-02-29",
    )


def test_resolve_date_range_handles_leap_day_when_adding_years() -> None:
    assert resolve_date_range("2024-02-29", None, 1) == (
        "2024-02-29",
        "2025-02-28",
    )


def test_resolve_date_range_uses_both_explicit_dates_without_applying_years() -> None:
    assert resolve_date_range("2024-01-01", "2024-06-01", 10) == (
        "2024-01-01",
        "2024-06-01",
    )


def test_resolve_date_range_uses_source_start_when_dates_are_omitted() -> None:
    assert resolve_date_range(None, None, 2, date(2021, 1, 4)) == (
        "2021-01-04",
        "2023-01-04",
    )


def test_resolve_date_range_rejects_start_on_or_after_end() -> None:
    with pytest.raises(ValueError, match="Start date must be before end date"):
        resolve_date_range("2024-01-02", "2024-01-02", 5)


def test_resolve_date_range_uses_today_when_end_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FixedDate(date):
        @classmethod
        def today(cls) -> "FixedDate":
            return cls(2026, 8, 19)

    monkeypatch.setattr(commands, "date", FixedDate)

    assert resolve_date_range(None, None, 2) == (
        "2024-08-19",
        "2026-08-19",
    )


def test_main_runs_backtest_from_csv_and_prints_parameters_and_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = FIXTURES_DIR / "cli_two_candles.csv"

    exit_code = main(
        [
            "backtest",
            "--source",
            "csv",
            "--csv-path",
            str(csv_path),
            "--symbol",
            "AAPL",
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-03",
            "--strategy",
            "buy-and-hold",
            "--initial-capital",
            "10000",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert "Backtest parameters" in captured.out
    assert "Strategy: Buy and Hold" in captured.out
    assert "Asset: AAPL" in captured.out
    assert (
        "Requested period: 2024-01-01 (inclusive) to 2024-01-03 (exclusive)"
        in captured.out
    )
    assert "Data used: 2024-01-01 through 2024-01-02 (2 candles)" in captured.out
    assert "Data span: 1 calendar day (0.00 years)" in captured.out
    assert (
        "Length in years: 5 (not applied because start and end were provided)"
        in captured.out
    )
    assert (
        "CSV period anchor: first CSV candle "
        "(not applied because a date boundary was provided)"
        in captured.out
    )
    assert f"Data source: csv, file: {csv_path.as_posix()}" in captured.out
    assert "Initial capital: 10,000.00" in captured.out
    assert "Position sizing: all in / all out" in captured.out
    assert "Commission: no commission" in captured.out
    assert "Slippage: 0.00%" in captured.out
    assert "Performance metrics" in captured.out
    assert "Total return: 10.00%" in captured.out
    assert "Number of trades: 1" in captured.out


def test_main_exports_backtest_chart_to_requested_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = FIXTURES_DIR / "cli_two_candles.csv"
    chart_path = tmp_path / "reports" / "backtest.png"
    export_dashboard = Mock(return_value=chart_path)
    monkeypatch.setattr(commands, "export_backtest_dashboard", export_dashboard)

    exit_code = main(
        [
            "backtest",
            "--source",
            "csv",
            "--csv-path",
            str(csv_path),
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-03",
            "--strategy",
            "buy-and-hold",
            "--chart",
            str(chart_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert f"Chart saved to: {chart_path}" in captured.out
    export_dashboard.assert_called_once()
    exported_result, exported_path = export_dashboard.call_args.args
    assert isinstance(exported_result, BacktestResult)
    assert exported_path == chart_path
    assert export_dashboard.call_args.kwargs == {
        "title": "Buy and Hold - SPY"
    }


@pytest.mark.parametrize("timestamp_column", ["timestamp", "datetime"])
def test_main_accepts_supported_csv_timestamp_aliases(
    timestamp_column: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text(
        (
            f"{timestamp_column},open,high,low,close,volume\n"
            "2024-01-01,100,100,100,100,1000\n"
            "2024-01-02,100,110,100,110,1200\n"
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "backtest",
            "--source",
            "csv",
            "--csv-path",
            str(csv_path),
            "--symbol",
            "AAPL",
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-03",
            "--strategy",
            "buy-and-hold",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert "Total return: 10.00%" in captured.out
    assert "Number of trades: 1" in captured.out


def test_main_runs_backtest_using_toml_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = (FIXTURES_DIR / "cli_two_candles.csv").as_posix()
    chart_path = tmp_path / "reports" / "backtest.png"
    export_dashboard = Mock(return_value=chart_path)
    monkeypatch.setattr(commands, "export_backtest_dashboard", export_dashboard)
    config_path = _write_config(
        tmp_path,
        f"""
[backtest]
source = "csv"
csv_path = "{csv_path}"
symbol = "AAPL"
start = "2024-01-01"
end = "2024-01-03"
strategy = "buy-and-hold"
initial_capital = 10000.0
chart = "{chart_path.as_posix()}"
""",
    )

    exit_code = main(["--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert "Strategy: Buy and Hold" in captured.out
    assert "Asset: AAPL" in captured.out
    assert "Total return: 10.00%" in captured.out
    assert f"Chart saved to: {chart_path}" in captured.out
    export_dashboard.assert_called_once()
    exported_result, exported_path = export_dashboard.call_args.args
    assert isinstance(exported_result, BacktestResult)
    assert exported_path == chart_path
    assert export_dashboard.call_args.kwargs == {
        "title": "Buy and Hold - AAPL"
    }


def test_main_reports_when_years_derived_the_requested_start(
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = FIXTURES_DIR / "cli_two_candles.csv"

    exit_code = main(
        [
            "backtest",
            "--source",
            "csv",
            "--csv-path",
            str(csv_path),
            "--end",
            "2024-01-03",
            "--years",
            "1",
            "--strategy",
            "buy-and-hold",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert (
        "Requested period: 2023-01-03 (inclusive) to 2024-01-03 (exclusive)"
        in captured.out
    )
    assert "Data used: 2024-01-01 through 2024-01-02 (2 candles)" in captured.out
    assert "Length in years: 1 (used to derive start)" in captured.out


def test_main_uses_years_to_derive_end_from_explicit_start(
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = FIXTURES_DIR / "cli_two_candles.csv"

    exit_code = main(
        [
            "backtest",
            "--source",
            "csv",
            "--csv-path",
            str(csv_path),
            "--start",
            "2024-01-01",
            "--years",
            "1",
            "--strategy",
            "buy-and-hold",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert (
        "Requested period: 2024-01-01 (inclusive) to 2025-01-01 (exclusive)"
        in captured.out
    )
    assert "Length in years: 1 (used to derive end)" in captured.out


def test_main_anchors_undated_csv_period_to_first_available_candle(
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = FIXTURES_DIR / "cli_two_candles.csv"

    exit_code = main(
        [
            "backtest",
            "--source",
            "csv",
            "--csv-path",
            str(csv_path),
            "--years",
            "1",
            "--strategy",
            "buy-and-hold",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert (
        "Requested period: 2024-01-01 (inclusive) to 2025-01-01 (exclusive)"
        in captured.out
    )
    assert "Data used: 2024-01-01 through 2024-01-02 (2 candles)" in captured.out
    assert "Length in years: 1 (used to derive end from CSV start)" in captured.out
    assert "CSV period anchor: first CSV candle (applied)" in captured.out


def test_main_can_anchor_undated_csv_period_to_today(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FixedDate(date):
        @classmethod
        def today(cls) -> "FixedDate":
            return cls(2024, 1, 3)

    monkeypatch.setattr(commands, "date", FixedDate)
    csv_path = FIXTURES_DIR / "cli_two_candles.csv"

    exit_code = main(
        [
            "backtest",
            "--source",
            "csv",
            "--csv-path",
            str(csv_path),
            "--csv-period-anchor",
            "end-today",
            "--years",
            "1",
            "--strategy",
            "buy-and-hold",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert (
        "Requested period: 2023-01-03 (inclusive) to 2024-01-03 (exclusive)"
        in captured.out
    )
    assert (
        "Length in years: 1 (used to derive start from today's end)"
        in captured.out
    )
    assert "CSV period anchor: today (applied)" in captured.out


def test_main_can_anchor_undated_csv_period_to_final_candle(
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = FIXTURES_DIR / "cli_two_candles.csv"

    exit_code = main(
        [
            "backtest",
            "--source",
            "csv",
            "--csv-path",
            str(csv_path),
            "--csv-period-anchor",
            "end-csv",
            "--years",
            "1",
            "--strategy",
            "buy-and-hold",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert (
        "Requested period: 2023-01-03 (inclusive) to 2024-01-03 (exclusive)"
        in captured.out
    )
    assert "Data used: 2024-01-01 through 2024-01-02 (2 candles)" in captured.out
    assert "Length in years: 1 (used to derive start from CSV end)" in captured.out
    assert (
        "CSV period anchor: last CSV candle "
        "(applied; final CSV candle included)"
        in captured.out
    )


def test_main_wires_toml_sizing_buffer_and_execution_costs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = (FIXTURES_DIR / "cli_two_candles.csv").as_posix()
    config_path = _write_config(
        tmp_path,
        f"""
[backtest]
source = "csv"
csv_path = "{csv_path}"
start = "2024-01-01"
end = "2024-01-03"
strategy = "buy-and-hold"
sizing = "fixed"
buy_size = 1
sell_size = 1
buffer_rate = 0.05
commission_model = "fixed"
fixed_commission = 5.0
slippage_rate = 0.1
""",
    )

    exit_code = main(["--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert (
        "Position sizing: fixed shares (buy=1, sell=1), cash buffer=5.00%"
        in captured.out
    )
    assert "Commission: fixed, 5.00 per trade" in captured.out
    assert "Slippage: 10.00%" in captured.out
    assert "Total return: -0.05%" in captured.out
    assert "Number of trades: 1" in captured.out


def test_main_runs_backtest_with_fixed_position_sizing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = FIXTURES_DIR / "cli_two_candles.csv"

    exit_code = main(
        [
            "backtest",
            "--source",
            "csv",
            "--csv-path",
            str(csv_path),
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-03",
            "--strategy",
            "buy-and-hold",
            "--sizing",
            "fixed",
            "--buy-size",
            "1",
            "--sell-size",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert "Position sizing: fixed shares (buy=1, sell=1)" in captured.out
    assert "Total return: 0.10%" in captured.out
    assert "Number of trades: 1" in captured.out


def test_main_applies_and_prints_buffered_position_sizing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = FIXTURES_DIR / "cli_two_candles.csv"

    exit_code = main(
        [
            "backtest",
            "--source",
            "csv",
            "--csv-path",
            str(csv_path),
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-03",
            "--strategy",
            "buy-and-hold",
            "--buffer-rate",
            "0.05",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert "Position sizing: all in / all out, cash buffer=5.00%" in captured.out


def test_main_applies_and_prints_fixed_commission_and_slippage(
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = FIXTURES_DIR / "cli_two_candles.csv"

    exit_code = main(
        [
            "backtest",
            "--source",
            "csv",
            "--csv-path",
            str(csv_path),
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-03",
            "--strategy",
            "buy-and-hold",
            "--sizing",
            "fixed",
            "--buy-size",
            "1",
            "--sell-size",
            "1",
            "--commission-model",
            "fixed",
            "--fixed-commission",
            "5",
            "--slippage-rate",
            "0.1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert "Commission: fixed, 5.00 per trade" in captured.out
    assert "Slippage: 10.00%" in captured.out
    assert "Total return: -0.05%" in captured.out
    assert "Number of trades: 1" in captured.out


def test_main_sizes_all_in_order_within_execution_cost_budget(
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = FIXTURES_DIR / "cli_two_candles.csv"

    exit_code = main(
        [
            "backtest",
            "--source",
            "csv",
            "--csv-path",
            str(csv_path),
            "--symbol",
            "AAPL",
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-03",
            "--strategy",
            "buy-and-hold",
            "--commission-model",
            "proportional",
            "--commission-rate",
            "0.001",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert "Number of trades: 1" in captured.out
    assert "Total return: 9.80%" in captured.out
    assert "Rejected orders" not in captured.out


@pytest.mark.parametrize("with_chart", [False, True])
def test_main_compares_strategy_with_benchmark_using_same_csv_data(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    with_chart: bool,
) -> None:
    csv_path = FIXTURES_DIR / "cli_two_candles.csv"
    chart_path = tmp_path / "comparison.png"
    exporter = Mock(return_value=chart_path)
    monkeypatch.setattr(commands, "export_comparison_dashboard", exporter)

    exit_code = main(
        [
            "compare",
            "--source",
            "csv",
            "--csv-path",
            str(csv_path),
            "--symbol",
            "AAPL",
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-03",
            "--strategy",
            "buy-and-hold",
            "--benchmark",
            "moving-average",
            *(["--chart", str(chart_path)] if with_chart else []),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert "Benchmark comparison parameters" in captured.out
    assert "Strategy: Buy and Hold" in captured.out
    assert (
        "Benchmark: Simple Moving Average Crossover with "
        "short window=20, long window=50"
        in captured.out
    )
    assert (
        "Requested period: 2024-01-01 (inclusive) to 2024-01-03 (exclusive)"
        in captured.out
    )
    assert "Data used: 2024-01-01 through 2024-01-02 (2 candles)" in captured.out
    assert "Metric comparison" in captured.out
    assert "Metric" in captured.out
    assert "Strategy" in captured.out
    assert "Benchmark" in captured.out
    assert "Difference" in captured.out
    assert "Total return" in captured.out
    assert "10.00%" in captured.out
    assert "Number of trades" in captured.out
    if with_chart:
        exporter.assert_called_once()
        strategy_result, benchmark_result, output_path = exporter.call_args.args
        assert strategy_result is not benchmark_result
        assert strategy_result.records[-1].snapshot.value == 11000
        assert benchmark_result.records[-1].snapshot.value == 10000
        assert output_path == chart_path
        metadata = exporter.call_args.kwargs
        assert metadata["strategy_name"] == "Buy and Hold"
        assert metadata["benchmark_name"].startswith("Simple Moving Average Crossover")
        assert "Benchmark sizing: all in / all out" in metadata["subtitle"]
        assert ("Total return", "10.00%", "0.00%") in metadata["metric_rows"]
        assert f"Chart saved to: {chart_path}" in captured.out
    else:
        exporter.assert_not_called()


def test_main_uses_all_in_all_out_for_benchmark_regardless_of_strategy_sizing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = FIXTURES_DIR / "cli_two_candles.csv"

    exit_code = main(
        [
            "compare",
            "--source",
            "csv",
            "--csv-path",
            str(csv_path),
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-03",
            "--strategy",
            "buy-and-hold",
            "--benchmark",
            "buy-and-hold",
            "--sizing",
            "fixed",
            "--buy-size",
            "1",
            "--sell-size",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert "Strategy position sizing: fixed shares (buy=1, sell=1)" in captured.out
    assert "Benchmark position sizing: all in / all out" in captured.out
    total_return_row = next(
        line for line in captured.out.splitlines() if line.startswith("Total return")
    )
    assert "0.10%" in total_return_row
    assert "10.00%" in total_return_row
    assert "-9.90%" in total_return_row


def test_main_reports_runtime_errors_and_returns_nonzero_exit_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = FIXTURES_DIR / "cli_one_candle.csv"

    exit_code = main(
        [
            "--source",
            "csv",
            "--csv-path",
            str(csv_path),
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-02",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert (
        captured.err
        == "Error: At least two candles are required to calculate metrics.\n"
    )


def _write_config(
    tmp_path: Path,
    contents: str,
    filename: str = "settings.toml",
) -> Path:
    path = tmp_path / filename
    path.write_text(contents.strip() + "\n", encoding="utf-8")
    return path
