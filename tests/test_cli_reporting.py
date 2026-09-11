from datetime import datetime
from io import StringIO
from pathlib import Path

import pytest

from backtester.cli.arguments import parse_args
from backtester.cli.reporting import (
    MAX_REJECTED_ORDER_DETAILS,
    describe_commission,
    describe_csv_period_anchor,
    describe_data_source,
    describe_sizing,
    describe_slippage,
    describe_strategy,
    format_metric_value,
    print_metric_comparison,
    print_rejected_orders,
)
from backtester.domain.trading import (
    Order,
    OrderExecutionResult,
    OrderExecutionStatus,
    Side,
)
from backtester.engine.backtest_result import BacktestResult
from backtester.metrics.benchmark_comparison import get_differences
from backtester.metrics.metrics import MetricData

@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (
            ["--short-window", "10", "--long-window", "40"],
            (
                "Simple Moving Average Crossover with "
                "short window=10, long window=40"
            ),
        ),
        (
            ["--strategy", "simple-moving-average"],
            (
                "Simple Moving Average Crossover with "
                "short window=20, long window=50"
            ),
        ),
        (
            ["--strategy", "exponential-moving-average"],
            (
                "Exponential Moving Average Crossover with "
                "short window=20, long window=50"
            ),
        ),
        (["--strategy", "buy-and-hold"], "Buy and Hold"),
        (
            [
                "--strategy",
                "rsi",
                "--rsi-period",
                "10",
                "--rsi-min",
                "25",
                "--rsi-max",
                "75",
            ],
            "Cutler RSI with period=10, min=25.0, max=75.0",
        ),
        (
            ["--strategy", "cutler-rsi"],
            "Cutler RSI with period=14, min=30.0, max=70.0",
        ),
        (
            ["--strategy", "exponential-rsi"],
            "Exponential RSI with period=14, min=30.0, max=70.0",
        ),
        (
            ["--strategy", "wilder-rsi"],
            "Wilder RSI with period=14, min=30.0, max=70.0",
        ),
        (
            [
                "--strategy",
                "mean-reversion",
                "--mean-window",
                "15",
                "--mean-threshold",
                "0.9",
            ],
            "Simple Mean Reversion with window=15, threshold=0.9",
        ),
        (
            ["--strategy", "simple-mean-reversion"],
            "Simple Mean Reversion with window=20, threshold=0.95",
        ),
        (
            ["--strategy", "exponential-mean-reversion"],
            "Exponential Mean Reversion with window=20, threshold=0.95",
        ),
        (
            [
                "--strategy",
                "donchian-breakout",
                "--entry-window",
                "55",
                "--exit-window",
                "21",
            ],
            "Donchian Breakout with entry window=55, exit window=21",
        ),
    ],
)
def test_describe_strategy_names_concrete_cli_strategy(
    arguments: list[str],
    expected: str,
) -> None:
    args = parse_args(arguments)

    assert describe_strategy(args.strategy, args) == expected


def test_describe_strategy_rejects_unknown_strategy() -> None:
    args = parse_args([])

    with pytest.raises(ValueError, match="Unknown strategy"):
        describe_strategy("unknown", args)


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ([], "Yahoo Finance"),
        (
            ["--source", "csv", "--csv-path", "data/AAPL.csv"],
            "csv, file: data/AAPL.csv",
        ),
    ],
)
def test_describe_data_source_uses_human_readable_names(
    arguments: list[str],
    expected: str,
) -> None:
    args = parse_args(arguments)

    assert describe_data_source(args) == expected


def test_describe_csv_directory_reports_effective_symbol_file(
    tmp_path: Path,
) -> None:
    args = parse_args(
        [
            "--source",
            "csv",
            "--csv-path",
            str(tmp_path),
            "--symbol",
            "AAPL",
        ]
    )

    assert describe_data_source(args) == (
        f"csv, file: {(tmp_path / 'AAPL.csv').as_posix()}"
    )


def test_describe_data_source_rejects_unknown_source() -> None:
    args = parse_args([])
    args.source = "unknown"

    with pytest.raises(ValueError, match="Unknown data source"):
        describe_data_source(args)


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ([], "all in / all out"),
        (
            ["--buffer-rate", "0.05"],
            "all in / all out, cash buffer=5.00%",
        ),
        (
            [
                "--sizing",
                "fixed",
                "--buy-size",
                "4",
                "--sell-size",
                "2",
            ],
            "fixed shares (buy=4, sell=2)",
        ),
        (
            [
                "--sizing",
                "fixed",
                "--buy-size",
                "4",
                "--sell-size",
                "2",
                "--buffer-rate",
                "0.025",
            ],
            "fixed shares (buy=4, sell=2), cash buffer=2.50%",
        ),
        (
            [
                "--sizing",
                "percent",
                "--buy-percent",
                "0.25",
                "--sell-percent",
                "1",
            ],
            "percentage (buy=25.00%, sell=100.00%)",
        ),
        (
            [
                "--sizing",
                "percent",
                "--buy-percent",
                "0.25",
                "--sell-percent",
                "1",
                "--buffer-rate",
                "0.05",
            ],
            "percentage (buy=25.00%, sell=100.00%), cash buffer=5.00%",
        ),
    ],
)
def test_describe_sizing_uses_human_readable_names(
    arguments: list[str],
    expected: str,
) -> None:
    args = parse_args(arguments)

    assert describe_sizing(args) == expected


def test_describe_sizing_rejects_unknown_policy() -> None:
    args = parse_args([])
    args.sizing = "unknown"

    with pytest.raises(ValueError, match="Unknown position sizing policy"):
        describe_sizing(args)


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ([], "no commission"),
        (
            [
                "--commission-model",
                "fixed",
                "--fixed-commission",
                "2.5",
            ],
            "fixed, 2.50 per trade",
        ),
        (
            [
                "--commission-model",
                "proportional",
                "--commission-rate",
                "0.001",
            ],
            "proportional, 0.10% of trade value",
        ),
    ],
)
def test_describe_commission_uses_human_readable_names(
    arguments: list[str],
    expected: str,
) -> None:
    args = parse_args(arguments)

    assert describe_commission(args) == expected


def test_describe_commission_rejects_unknown_model() -> None:
    args = parse_args([])
    args.commission_model = "unknown"

    with pytest.raises(ValueError, match="Unknown commission model"):
        describe_commission(args)


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ([], "0.00%"),
        (["--slippage-rate", "0.0005"], "0.05%"),
        (["--slippage-rate", "0.1"], "10.00%"),
    ],
)
def test_describe_slippage_uses_human_readable_percentage(
    arguments: list[str],
    expected: str,
) -> None:
    args = parse_args(arguments)

    assert describe_slippage(args) == expected


@pytest.mark.parametrize(
    ("anchor", "expected"),
    [
        ("start-csv", "first CSV candle"),
        ("end-today", "today"),
        ("end-csv", "last CSV candle"),
    ],
)
def test_describe_csv_period_anchor_uses_human_readable_names(
    anchor: str,
    expected: str,
) -> None:
    assert describe_csv_period_anchor(anchor) == expected


def test_describe_csv_period_anchor_rejects_unknown_anchor() -> None:
    with pytest.raises(ValueError, match="Unknown CSV period anchor"):
        describe_csv_period_anchor("unknown")


@pytest.mark.parametrize(
    ("status", "expected_reason"),
    [
        (OrderExecutionStatus.INSUFFICIENT_FUNDS, "Insufficient funds"),
        (OrderExecutionStatus.INSUFFICIENT_POSITION, "Insufficient position"),
    ],
)
def test_print_rejected_orders_uses_execution_status(
    status: OrderExecutionStatus,
    expected_reason: str,
) -> None:
    execution = OrderExecutionResult(
        order=Order(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100,
            signal_timestamp=datetime(2023, 12, 31),
            submitted_timestamp=datetime(2024, 1, 1),
        ),
        status=status,
        trade=None,
    )
    result = BacktestResult(
        symbols=("AAPL",),
        initial_cash=1_000,
        records=[],
        trades=[],
        order_executions=[execution],
    )
    output = StringIO()

    print_rejected_orders(output, "Rejected orders", result)

    report = output.getvalue()
    assert "Rejected orders: 1" in report
    assert expected_reason in report


def test_rejected_order_details_are_omitted_above_display_limit() -> None:
    rejected_orders = [
        OrderExecutionResult(
            order=Order(
                symbol="AAPL",
                side=Side.BUY,
                quantity=100,
                signal_timestamp=datetime(2023, 12, 31),
                submitted_timestamp=datetime(2024, 1, 1),
            ),
            status=OrderExecutionStatus.INSUFFICIENT_FUNDS,
            trade=None
        )
        for _ in range(MAX_REJECTED_ORDER_DETAILS + 1)
    ]
    result = BacktestResult(
        symbols=("AAPL",),
        initial_cash=1_000,
        records=[],
        trades=[],
        order_executions=rejected_orders,
    )
    output = StringIO()

    print_rejected_orders(output, "Rejected orders", result)

    report = output.getvalue()
    assert f"Rejected orders: {len(rejected_orders)}" in report
    assert (
        "Details omitted because the rejected-order limit is "
        f"{MAX_REJECTED_ORDER_DETAILS}."
    ) in report
    assert "Order time" not in report


def test_print_metric_comparison_shows_strategy_benchmark_and_difference() -> None:
    output = StringIO()
    strategy_metrics = {
        "total_return": MetricData("Total return", 0.25),
        "number_of_trades": MetricData("Number of trades", 3),
    }
    benchmark_metrics = {
        "total_return": MetricData("Total return", 0.20),
        "number_of_trades": MetricData("Number of trades", 1),
    }
    differences = get_differences(strategy_metrics, benchmark_metrics)

    print_metric_comparison(
        output,
        strategy_metrics,
        benchmark_metrics,
        differences,
    )

    lines = output.getvalue().splitlines()
    assert lines[0] == "Metric comparison"
    assert lines[1].split() == ["Metric", "Strategy", "Benchmark", "Difference"]
    assert lines[2].split() == ["Total", "return", "25.00%", "20.00%", "5.00%"]
    assert lines[3].split() == ["Number", "of", "trades", "3", "1", "2"]


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("total_return", 0.12345, "12.35%"),
        ("daily_sharpe_ratio", 1.23456, "1.2346"),
        ("number_of_trades", 3.0, "3"),
        ("daily_sharpe_ratio", float("nan"), "N/A"),
        ("daily_sharpe_ratio", float("inf"), "N/A"),
    ],
)
def test_format_metric_value_uses_metric_specific_formatting(
    name: str,
    value: float,
    expected: str,
) -> None:
    assert format_metric_value(name, value) == expected
