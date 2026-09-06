"""High-level workflows executed by Strat Echo CLI commands."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from typing import Sequence, TextIO

from backtester.cli import factories, reporting
from backtester.data.loader import (
    CSVDataSource,
    DataSource,
    candles_from_dataframe,
)
from backtester.domain.market import Candle
from backtester.engine.backtest import BacktestEngine
from backtester.engine.backtest_result import BacktestResult
from backtester.execution.broker import Broker
from backtester.execution.costs import CommissionModel, ExecutionModel
from backtester.metrics.benchmark_comparison import get_differences
from backtester.portfolio.portfolio import Portfolio
from backtester.sizing.policy import SizingPlan
from backtester.strategies.base import SingleAssetStrategy
from backtester.visualization.export import (
    export_backtest_dashboard,
    export_comparison_dashboard,
)


def run_backtest_command(args: argparse.Namespace, output: TextIO) -> None:
    """Run one configured backtest and print its parameters and results."""
    data_source = factories.create_data_source(args)
    start, end = _resolve_command_date_range(args, data_source)
    strategy = factories.create_strategy(args.strategy, args)
    result = _run_backtest(args, data_source, strategy, start, end)
    metrics = factories.create_performance_analyzer().calculate_metrics(result)
    strategy_description = reporting.describe_strategy(args.strategy, args)

    reporting.print_parameters(
        output=output,
        title="Backtest parameters",
        strategy_name=strategy_description,
        benchmark_name=None,
        symbol=args.symbol,
        start=start,
        end=end,
        years=args.years,
        years_note=_describe_years_application(args),
        csv_period_anchor=_reported_csv_period_anchor(args),
        csv_period_anchor_applied=_csv_period_anchor_is_applied(args),
        result=result,
        data_source_name=reporting.describe_data_source(args),
        initial_capital=args.initial_capital,
        sizing_name=reporting.describe_sizing(args),
        commission_name=reporting.describe_commission(args),
        slippage_name=reporting.describe_slippage(args),
    )
    reporting.print_metrics(output, "Performance metrics", metrics)
    reporting.print_rejected_orders(output, "Rejected orders", result)

    if args.chart_path is not None:
        chart_path = export_backtest_dashboard(
            result,
            args.chart_path,
            title=f"{strategy_description} - {result.symbol}",
        )
        print(file=output)
        print(f"Chart saved to: {chart_path}", file=output)


def run_compare_command(args: argparse.Namespace, output: TextIO) -> None:
    """Run a strategy and benchmark over identical data and print differences."""
    data_source = factories.create_data_source(args)
    start, end = _resolve_command_date_range(args, data_source)
    data = data_source.load(args.symbol, start, end)
    if data is None or data.empty:
        raise ValueError("No market data was returned for the selected parameters.")

    candles = candles_from_dataframe(data)
    _validate_backtest_data(candles)

    strategy_result = _run_backtest_with_candles(
        strategy=factories.create_strategy(args.strategy, args),
        candles=candles,
        symbol=args.symbol,
        initial_capital=args.initial_capital,
        sizing_plan=factories.create_sizing_plan(args),
        execution_model=factories.create_execution_model(args),
        commission_model=factories.create_commission_model(args),
        buffer_rate=args.buffer_rate,
    )
    benchmark_result = _run_backtest_with_candles(
        strategy=factories.create_strategy(args.benchmark, args),
        candles=candles,
        symbol=args.symbol,
        initial_capital=args.initial_capital,
        sizing_plan=factories.create_all_in_all_out_sizing_plan(),
        execution_model=factories.create_execution_model(args),
        commission_model=factories.create_commission_model(args),
        buffer_rate=args.buffer_rate,
    )

    analyzer = factories.create_performance_analyzer()
    strategy_metrics = analyzer.calculate_metrics(strategy_result)
    benchmark_metrics = analyzer.calculate_metrics(benchmark_result)
    differences = get_differences(strategy_metrics, benchmark_metrics)

    reporting.print_parameters(
        output=output,
        title="Benchmark comparison parameters",
        strategy_name=reporting.describe_strategy(args.strategy, args),
        benchmark_name=reporting.describe_strategy(args.benchmark, args),
        symbol=args.symbol,
        start=start,
        end=end,
        years=args.years,
        years_note=_describe_years_application(args),
        csv_period_anchor=_reported_csv_period_anchor(args),
        csv_period_anchor_applied=_csv_period_anchor_is_applied(args),
        result=strategy_result,
        data_source_name=reporting.describe_data_source(args),
        initial_capital=args.initial_capital,
        sizing_name=reporting.describe_sizing(args),
        benchmark_sizing_name=reporting.describe_all_in_all_out_sizing(args),
        commission_name=reporting.describe_commission(args),
        slippage_name=reporting.describe_slippage(args),
    )
    reporting.print_metric_comparison(
        output,
        strategy_metrics,
        benchmark_metrics,
        differences,
    )
    reporting.print_rejected_orders(
        output,
        "Strategy rejected orders",
        strategy_result,
    )
    reporting.print_rejected_orders(
        output,
        "Benchmark rejected orders",
        benchmark_result,
    )

    if args.chart_path is not None:
        metric_rows = [
            (
                metric.label,
                reporting.format_metric_value(name, metric.result),
                reporting.format_metric_value(name, benchmark_metrics[name].result),
            )
            for name, metric in strategy_metrics.items()
            if name in benchmark_metrics
        ]
        chart_path = export_comparison_dashboard(
            strategy_result,
            benchmark_result,
            args.chart_path,
            strategy_name=reporting.describe_strategy(args.strategy, args),
            benchmark_name=reporting.describe_strategy(args.benchmark, args),
            subtitle=(
                f"Strategy sizing: {reporting.describe_sizing(args)}\n"
                f"Benchmark sizing: {reporting.describe_all_in_all_out_sizing(args)}"
            ),
            metric_rows=metric_rows,
        )
        print(file=output)
        print(f"Chart saved to: {chart_path}", file=output)


def _run_backtest(
    args: argparse.Namespace,
    data_source: DataSource,
    strategy: SingleAssetStrategy,
    start: str,
    end: str,
) -> BacktestResult:
    data = data_source.load(args.symbol, start, end)
    if data is None or data.empty:
        raise ValueError("No market data was returned for the selected parameters.")

    candles = candles_from_dataframe(data)
    _validate_backtest_data(candles)
    return _run_backtest_with_candles(
        strategy=strategy,
        candles=candles,
        symbol=args.symbol,
        initial_capital=args.initial_capital,
        sizing_plan=factories.create_sizing_plan(args),
        execution_model=factories.create_execution_model(args),
        commission_model=factories.create_commission_model(args),
        buffer_rate=args.buffer_rate,
    )


def _run_backtest_with_candles(
    strategy: SingleAssetStrategy,
    candles: Sequence[Candle],
    symbol: str,
    initial_capital: float,
    sizing_plan: SizingPlan,
    execution_model: ExecutionModel,
    commission_model: CommissionModel,
    buffer_rate: float | None,
) -> BacktestResult:
    broker = Broker(
        Portfolio(cash=initial_capital),
        execution_model=execution_model,
        commission_model=commission_model,
    )
    return BacktestEngine(
        strategy=strategy,
        broker=broker,
        plan=sizing_plan,
        resolver=factories.create_order_resolver(
            execution_model=execution_model,
            commission_model=commission_model,
            buffer_rate=buffer_rate,
        ),
        data=candles,
        symbol=symbol,
    ).run()


def resolve_date_range(
    start_arg: str | None,
    end_arg: str | None,
    years: int,
    source_start: date | None = None,
) -> tuple[str, str]:
    """Resolve an inclusive start and exclusive end date for data loading.

    Years determine whichever explicit boundary is missing. When both are
    missing, ``source_start`` anchors the range when supplied; otherwise the
    end defaults to today. February 29 is adjusted to February 28 when the
    shifted year is not a leap year.
    """
    if start_arg is not None:
        start = date.fromisoformat(start_arg)
        end = (
            date.fromisoformat(end_arg)
            if end_arg is not None
            else _add_years(start, years)
        )
    elif end_arg is not None:
        end = date.fromisoformat(end_arg)
        start = _subtract_years(end, years)
    elif source_start is not None:
        start = source_start
        end = _add_years(start, years)
    else:
        end = date.today()
        start = _subtract_years(end, years)

    if start >= end:
        raise ValueError("Start date must be before end date.")

    return start.isoformat(), end.isoformat()


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def _add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def _resolve_command_date_range(
    args: argparse.Namespace,
    data_source: DataSource,
) -> tuple[str, str]:
    source_start = None
    if (
        args.start is None
        and args.end is None
        and isinstance(data_source, CSVDataSource)
    ):
        if args.csv_period_anchor == "start-csv":
            source_start = data_source.first_available_date(args.symbol)
        elif args.csv_period_anchor == "end-csv":
            last_date = data_source.last_available_date(args.symbol)
            exclusive_end = last_date + timedelta(days=1)
            return resolve_date_range(
                args.start,
                exclusive_end.isoformat(),
                args.years,
            )

    return resolve_date_range(args.start, args.end, args.years, source_start)


def _describe_years_application(args: argparse.Namespace) -> str:
    if args.start is not None and args.end is not None:
        return "not applied because start and end were provided"
    if args.start is not None:
        return "used to derive end"
    if args.end is not None:
        return "used to derive start"
    if args.source == "csv" and args.csv_period_anchor == "start-csv":
        return "used to derive end from CSV start"
    if args.source == "csv" and args.csv_period_anchor == "end-csv":
        return "used to derive start from CSV end"
    return "used to derive start from today's end"


def _reported_csv_period_anchor(args: argparse.Namespace) -> str | None:
    if args.source != "csv":
        return None
    return args.csv_period_anchor


def _csv_period_anchor_is_applied(args: argparse.Namespace) -> bool:
    return args.source == "csv" and args.start is None and args.end is None


def _validate_backtest_data(candles: Sequence[Candle]) -> None:
    if len(candles) < 2:
        raise ValueError("At least two candles are required to calculate metrics.")
