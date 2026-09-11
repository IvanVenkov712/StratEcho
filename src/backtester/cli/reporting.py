"""Plain-text formatting and reporting for CLI backtest results."""

from __future__ import annotations

import argparse
import math
from datetime import datetime
from typing import TextIO

from backtester.domain.trading import OrderExecutionStatus
from backtester.engine.backtest_result import BacktestResult
from backtester.metrics.metrics import MetricData


MAX_REJECTED_ORDER_DETAILS = 10

PERCENT_METRICS = {
    "total_return",
    "annualized_return",
    "daily_avg",
    "daily_volatility",
    "annual_volatility",
    "max_drawdown",
}

REJECTION_MESSAGES = {
    OrderExecutionStatus.INSUFFICIENT_FUNDS: "Insufficient funds",
    OrderExecutionStatus.INSUFFICIENT_POSITION: "Insufficient position",
}

STRATEGY_DISPLAY_NAMES = {
    "buy-and-hold": "Buy and Hold",
    "moving-average": "Simple Moving Average Crossover",
    "simple-moving-average": "Simple Moving Average Crossover",
    "exponential-moving-average": "Exponential Moving Average Crossover",
    "rsi": "Cutler RSI",
    "cutler-rsi": "Cutler RSI",
    "exponential-rsi": "Exponential RSI",
    "wilder-rsi": "Wilder RSI",
    "mean-reversion": "Simple Mean Reversion",
    "simple-mean-reversion": "Simple Mean Reversion",
    "exponential-mean-reversion": "Exponential Mean Reversion",
    "donchian-breakout": "Donchian Breakout",
}

CSV_PERIOD_ANCHOR_DISPLAY_NAMES = {
    "start-csv": "first CSV candle",
    "end-today": "today",
    "end-csv": "last CSV candle",
}


def print_parameters(
    *,
    output: TextIO,
    title: str,
    strategy_name: str,
    benchmark_name: str | None,
    symbol: str,
    start: str,
    end: str,
    years: int,
    years_note: str,
    csv_period_anchor: str | None,
    csv_period_anchor_applied: bool,
    result: BacktestResult,
    data_source_name: str,
    initial_capital: float,
    sizing_name: str,
    benchmark_sizing_name: str | None = None,
    commission_name: str,
    slippage_name: str,
    allocations: dict[str, float] | None = None,
    priorities: dict[str, int] | None = None,
) -> None:
    """Print the effective parameters of a backtest or comparison."""
    print(title, file=output)
    print(f"Strategy: {strategy_name}", file=output)
    if benchmark_name is not None:
        print(f"Benchmark: {benchmark_name}", file=output)
    label = "Assets" if allocations and len(allocations) > 1 else "Asset"
    print(f"{label}: {symbol}", file=output)
    if allocations is not None:
        print("Allocations: " + ", ".join(
            f"{symbol}={weight:.2%}" for symbol, weight in allocations.items()
        ), file=output)
    if priorities is not None:
        ordered = sorted(priorities, key=lambda symbol: (priorities[symbol], symbol))
        print("Priorities: " + ", ".join(
            f"{symbol}={priorities[symbol]}" for symbol in ordered
        ), file=output)
        print("Execution order: sells before buys; within each side: " + ", ".join(ordered), file=output)
    print(
        f"Requested period: {start} (inclusive) to {end} (exclusive)",
        file=output,
    )
    _print_data_period(output, result)
    print(f"Length in years: {years} ({years_note})", file=output)
    if csv_period_anchor is not None:
        if csv_period_anchor_applied and csv_period_anchor == "end-csv":
            anchor_note = "applied; final CSV candle included"
        elif csv_period_anchor_applied:
            anchor_note = "applied"
        else:
            anchor_note = "not applied because a date boundary was provided"
        print(
            "CSV period anchor: "
            f"{describe_csv_period_anchor(csv_period_anchor)} ({anchor_note})",
            file=output,
        )
    print(f"Data source: {data_source_name}", file=output)
    print(f"Initial capital: {_format_money(initial_capital)}", file=output)
    if benchmark_sizing_name is None:
        print(f"Position sizing: {sizing_name}", file=output)
    else:
        print(f"Strategy position sizing: {sizing_name}", file=output)
        print(f"Benchmark position sizing: {benchmark_sizing_name}", file=output)
    print(f"Commission: {commission_name}", file=output)
    print(f"Slippage: {slippage_name}", file=output)
    print(file=output)


def _print_data_period(output: TextIO, result: BacktestResult) -> None:
    """Print the actual candle coverage used by the backtest."""
    first_timestamp = result.records[0].timestamp
    last_timestamp = result.records[-1].timestamp
    observation_count = len(result.records)
    observation_label = "frames" if len(result.symbols) > 1 else "candles"

    print(
        "Data used: "
        f"{_format_date(first_timestamp)} through {_format_date(last_timestamp)} "
        f"({observation_count:,} {observation_label})",
        file=output,
    )

    elapsed_days = (
        last_timestamp - first_timestamp
    ).total_seconds() / (24.0 * 60.0 * 60.0)
    elapsed_years = elapsed_days / 365.25
    print(
        f"Data span: {_format_day_count(elapsed_days)} calendar "
        f"{'day' if elapsed_days == 1 else 'days'} "
        f"({elapsed_years:.2f} years)",
        file=output,
    )


def _format_date(value: datetime) -> str:
    return value.date().isoformat()


def _format_day_count(value: float) -> str:
    if value.is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}"


def print_metrics(
    output: TextIO,
    title: str,
    metrics: dict[str, MetricData],
) -> None:
    """Print labeled metric values in analyzer registration order."""
    print(title, file=output)
    for name, data in metrics.items():
        print(f"{data.label}: {format_metric_value(name, data.result)}", file=output)


def print_metric_comparison(
    output: TextIO,
    strategy_metrics: dict[str, MetricData],
    benchmark_metrics: dict[str, MetricData],
    differences: dict[str, MetricData],
) -> None:
    """Print common metrics and their strategy-minus-benchmark differences."""
    rows: list[tuple[str, str, str, str]] = []
    for name, difference_data in differences.items():
        strategy_data = strategy_metrics.get(name)
        benchmark_data = benchmark_metrics.get(name)
        if strategy_data is None or benchmark_data is None:
            continue

        rows.append(
            (
                strategy_data.label,
                format_metric_value(name, strategy_data.result),
                format_metric_value(name, benchmark_data.result),
                format_metric_value(name, difference_data.result),
            )
        )

    headers = ("Metric", "Strategy", "Benchmark", "Difference")
    widths = [
        max(len(header), *(len(row[index]) for row in rows))
        for index, header in enumerate(headers)
    ]

    print("Metric comparison", file=output)
    print(
        f"{headers[0]:<{widths[0]}}  "
        f"{headers[1]:>{widths[1]}}  "
        f"{headers[2]:>{widths[2]}}  "
        f"{headers[3]:>{widths[3]}}",
        file=output,
    )
    for label, strategy_value, benchmark_value, difference_value in rows:
        print(
            f"{label:<{widths[0]}}  "
            f"{strategy_value:>{widths[1]}}  "
            f"{benchmark_value:>{widths[2]}}  "
            f"{difference_value:>{widths[3]}}",
            file=output,
        )


def print_rejected_orders(
    output: TextIO,
    title: str,
    result: BacktestResult,
) -> None:
    """Print a bounded summary of orders rejected during a backtest."""
    rejected_orders = [
        execution
        for execution in result.order_executions
        if execution.status is not OrderExecutionStatus.SUCCESS
    ]
    if not rejected_orders:
        return

    print(file=output)
    print(f"{title}: {len(rejected_orders)}", file=output)

    if len(rejected_orders) > MAX_REJECTED_ORDER_DETAILS:
        print(
            "Details omitted because the rejected-order limit is "
            f"{MAX_REJECTED_ORDER_DETAILS}.",
            file=output,
        )
        return

    for execution in rejected_orders:
        order = execution.order
        print(
            "- Order time "
            f"{order.submitted_timestamp.isoformat(sep=' ')} | "
            f"{order.side.value.upper()} {order.quantity} {order.symbol} | "
            f"{_format_rejection_status(execution.status)}",
            file=output,
        )


def _format_rejection_status(status: OrderExecutionStatus) -> str:
    return REJECTION_MESSAGES.get(status, "Unknown rejection reason")


def format_metric_value(name: str, value: float) -> str:
    """Format a metric according to its semantic type for CLI output."""
    if isinstance(value, float) and not math.isfinite(value):
        return "N/A"

    if name in PERCENT_METRICS:
        return f"{value:.2%}"

    if name == "number_of_trades":
        return str(int(value))

    return f"{value:.4f}"


def _format_money(value: float) -> str:
    return f"{value:,.2f}"


def describe_strategy(name: str, args: argparse.Namespace) -> str:
    """Return a human-readable description of a configured strategy."""
    try:
        display_name = STRATEGY_DISPLAY_NAMES[name]
    except KeyError:
        raise ValueError(f"Unknown strategy: {name}.") from None

    if name in {
        "moving-average",
        "simple-moving-average",
        "exponential-moving-average",
    }:
        return (
            f"{display_name} with short window={args.short_window}, "
            f"long window={args.long_window}"
        )
    if name == "buy-and-hold":
        return display_name
    if name in {
        "rsi",
        "cutler-rsi",
        "exponential-rsi",
        "wilder-rsi",
    }:
        return (
            f"{display_name} with period={args.rsi_period}, "
            f"min={args.rsi_min}, max={args.rsi_max}"
        )
    if name in {
        "mean-reversion",
        "simple-mean-reversion",
        "exponential-mean-reversion",
    }:
        return (
            f"{display_name} with window={args.mean_window}, "
            f"threshold={args.mean_threshold}"
        )
    if name == "donchian-breakout":
        return (
            f"{display_name} with entry window={args.entry_window}, "
            f"exit window={args.exit_window}"
        )

    raise ValueError(f"Unknown strategy: {name}.")


def describe_data_source(args: argparse.Namespace) -> str:
    """Return a human-readable description of the configured data source."""
    if args.source == "yfinance":
        return "Yahoo Finance"
    if args.source == "csv":
        if args.csv_path is None:
            raise ValueError("CSV file path is required for the CSV data source.")

        csv_path = args.csv_path
        if csv_path.is_dir():
            if len(args.symbols) > 1:
                return f"csv, directory: {csv_path.as_posix()} (SYMBOL.csv per asset)"
            csv_path = csv_path / f"{args.symbol}.csv"
        display_path = csv_path.as_posix()
        return f"csv, file: {display_path}"

    raise ValueError(f"Unknown data source: {args.source}.")


def describe_sizing(args: argparse.Namespace) -> str:
    """Return a human-readable description of sizing and any cash buffer."""
    if args.sizing == "all-in-all-out":
        description = "all in / all out"
    elif args.sizing == "fixed":
        description = f"fixed shares (buy={args.buy_size}, sell={args.sell_size})"
    elif args.sizing == "percent":
        description = (
            "percentage ("
            f"buy={args.buy_percent:.2%}, sell={args.sell_percent:.2%}"
            ")"
        )
    else:
        raise ValueError(f"Unknown position sizing policy: {args.sizing}.")

    if args.buffer_rate is not None:
        return f"{description}, cash buffer={args.buffer_rate:.2%}"

    return description


def describe_universe_sizing(args: argparse.Namespace) -> str:
    """Show the shared sizing once, or label each symbol's individual sizing."""
    descriptions = {
        symbol: describe_sizing(settings)
        for symbol, settings in args.sizing_by_symbol.items()
    }
    if len(set(descriptions.values())) == 1:
        return next(iter(descriptions.values()))
    return "; ".join(f"{symbol}: {description}" for symbol, description in descriptions.items())


def describe_all_in_all_out_sizing(args: argparse.Namespace) -> str:
    """Describe benchmark all-in/all-out sizing and its shared cash buffer."""
    description = "all in / all out"
    if args.buffer_rate is not None:
        description += f", cash buffer={args.buffer_rate:.2%}"
    return description


def describe_commission(args: argparse.Namespace) -> str:
    """Return a human-readable description of the configured commission."""
    if args.commission_model == "none":
        return "no commission"
    if args.commission_model == "fixed":
        return f"fixed, {_format_money(args.fixed_commission)} per trade"
    if args.commission_model == "proportional":
        return f"proportional, {args.commission_rate:.2%} of trade value"

    raise ValueError(f"Unknown commission model: {args.commission_model}.")


def describe_slippage(args: argparse.Namespace) -> str:
    """Return the configured slippage as a human-readable percentage."""
    return f"{args.slippage_rate:.2%}"


def describe_csv_period_anchor(anchor: str) -> str:
    """Return a human-readable description of a CSV date-range anchor."""
    try:
        return CSV_PERIOD_ANCHOR_DISPLAY_NAMES[anchor]
    except KeyError:
        raise ValueError(f"Unknown CSV period anchor: {anchor}.") from None
