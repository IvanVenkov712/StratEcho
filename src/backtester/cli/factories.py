"""Factories that translate parsed CLI settings into backtest components."""

from __future__ import annotations

import argparse

import pandas as pd

from backtester.data.loader import CSVDataSource, DataSource, YFinanceDataSource, normalize_column_names
from backtester.domain.trading import SizingInstruction, SizingMode
from backtester.execution.costs import (
    CommissionModel,
    ExecutionCostCalculator,
    ExecutionModel,
    FixedCommissionModel,
    NoCommissionModel,
    ProportionalCommissionModel,
)
from backtester.metrics.metrics import (
    PerformanceAnalyzer,
    annual_sharpe_ratio,
    annual_volatility,
    annualized_return,
    daily_avg,
    daily_sharpe_ratio,
    daily_volatility,
    max_drawdown,
    number_of_trades,
    total_return,
)
from backtester.resolving.resolver import (
    BufferQuantityResolver,
    BuyQuantityCapper,
    OrderResolver,
    QuantityResolver,
)
from backtester.sizing.policy import MultiAssetSizingPlan, SizingPlan
from backtester.strategies.base import SingleAssetStrategy
from backtester.strategies.multi_asset.simple_multi_asset import SimpleMultiAssetStrategy
from backtester.strategies.breakout import DonchianBreakoutStrategy
from backtester.strategies.buy_n_hold import BuyAndHoldStrategy
from backtester.strategies.moving_average import (
    ExponentialMovingAverageCrossStrategy,
    SimpleMovingAverageCrossStrategy,
)
from backtester.strategies.mrma import (
    ExponentialMeanReversionStrategy,
    SimpleMeanReversionStrategy,
)
from backtester.strategies.rsi_strategies import (
    CutlerRSIStrategy,
    ExponentialRSIStrategy,
    WilderRSIStrategy,
)


def create_performance_analyzer() -> PerformanceAnalyzer:
    """Create an analyzer containing the standard Strat Echo metrics."""
    analyzer = PerformanceAnalyzer()
    analyzer.add_metric_func("total_return", "Total return", total_return)
    analyzer.add_metric_func("annualized_return", "Annualized return", annualized_return)
    analyzer.add_metric_func("daily_avg", "Daily average return", daily_avg)
    analyzer.add_metric_func("daily_volatility", "Daily volatility", daily_volatility)
    analyzer.add_metric_func("annual_volatility", "Annual volatility", annual_volatility)
    analyzer.add_metric_func("max_drawdown", "Maximum drawdown", max_drawdown)
    analyzer.add_metric_func(
        "daily_sharpe_ratio",
        "Daily Sharpe ratio",
        daily_sharpe_ratio,
    )
    analyzer.add_metric_func(
        "annual_sharpe_ratio",
        "Annual Sharpe ratio",
        annual_sharpe_ratio,
    )
    analyzer.add_metric_func("number_of_trades", "Number of trades", number_of_trades)
    return analyzer


def create_strategy(name: str, args: argparse.Namespace) -> SingleAssetStrategy:
    """Create the named strategy from parsed CLI parameters."""
    if name in {"moving-average", "simple-moving-average"}:
        return SimpleMovingAverageCrossStrategy(
            short_window_size=args.short_window,
            long_window_size=args.long_window,
        )
    if name == "exponential-moving-average":
        return ExponentialMovingAverageCrossStrategy(
            short_window_size=args.short_window,
            long_window_size=args.long_window,
        )
    if name == "buy-and-hold":
        return BuyAndHoldStrategy()
    if name in {"rsi", "cutler-rsi"}:
        return CutlerRSIStrategy(
            min=args.rsi_min,
            max=args.rsi_max,
            window_size=args.rsi_period,
        )
    if name == "exponential-rsi":
        return ExponentialRSIStrategy(
            min=args.rsi_min,
            max=args.rsi_max,
            window_size=args.rsi_period,
        )
    if name == "wilder-rsi":
        return WilderRSIStrategy(
            min=args.rsi_min,
            max=args.rsi_max,
            window_size=args.rsi_period,
        )
    if name in {"mean-reversion", "simple-mean-reversion"}:
        return SimpleMeanReversionStrategy(
            window=args.mean_window,
            threshold=args.mean_threshold,
        )
    if name == "exponential-mean-reversion":
        return ExponentialMeanReversionStrategy(
            window=args.mean_window,
            threshold=args.mean_threshold,
        )
    if name == "donchian-breakout":
        return DonchianBreakoutStrategy(
            entry_window=args.entry_window,
            exit_window=args.exit_window,
        )

    raise ValueError(f"Unknown strategy: {name}.")


def create_multi_asset_strategy(name: str, args: argparse.Namespace) -> SimpleMultiAssetStrategy:
    """Give each symbol a fresh strategy with the shared parameter values."""
    return SimpleMultiAssetStrategy({
        symbol: create_strategy(name, args) for symbol in args.symbols
    })


def create_multi_asset_sizing_plan(
    args: argparse.Namespace, *, benchmark: bool = False,
) -> MultiAssetSizingPlan:
    """Build each symbol's effective sizing, or all-in/all-out for a benchmark."""
    return MultiAssetSizingPlan({
        symbol: (
            create_all_in_all_out_sizing_plan() if benchmark
            else create_sizing_plan(args.sizing_by_symbol[symbol])
        )
        for symbol in args.symbols
    })


def create_sizing_plan(args: argparse.Namespace) -> SizingPlan:
    """Create buy and sell sizing instructions from parsed CLI parameters."""
    if args.sizing == "all-in-all-out":
        return create_all_in_all_out_sizing_plan()
    elif args.sizing == "fixed":
        buy_instruction = SizingInstruction(
            mode=SizingMode.FIXED,
            value=args.buy_size,
        )
        sell_instruction = SizingInstruction(
            mode=SizingMode.FIXED,
            value=args.sell_size,
        )
    elif args.sizing == "percent":
        buy_instruction = SizingInstruction(
            mode=SizingMode.PERCENT,
            value=args.buy_percent,
        )
        sell_instruction = SizingInstruction(
            mode=SizingMode.PERCENT,
            value=args.sell_percent,
        )
    else:
        raise ValueError(f"Unknown position sizing policy: {args.sizing}.")

    return SizingPlan(buy=buy_instruction, sell=sell_instruction)


def create_all_in_all_out_sizing_plan() -> SizingPlan:
    """Create a plan that invests available cash and fully exits positions."""
    instruction = SizingInstruction(mode=SizingMode.ALL_IN, value=None)
    return SizingPlan(buy=instruction, sell=instruction)


def create_order_resolver(
    execution_model: ExecutionModel,
    commission_model: CommissionModel,
    buffer_rate: float | None,
) -> OrderResolver:
    """Create a cost-aware order resolver with an optional cash buffer."""
    cost_calculator = ExecutionCostCalculator(
        execution_model=execution_model,
        commission_model=commission_model,
    )
    buy_quantity_capper = BuyQuantityCapper(cost_calculator)
    quantity_resolver = QuantityResolver(buy_quantity_capper)

    if buffer_rate is not None:
        quantity_resolver = BufferQuantityResolver(
            resolver=quantity_resolver,
            capper=buy_quantity_capper,
            buffer_rate=buffer_rate,
        )

    return OrderResolver(quantity_resolver)


def create_execution_model(args: argparse.Namespace) -> ExecutionModel:
    """Create the adverse-slippage execution model selected by the CLI."""
    return ExecutionModel(slippage_rate=args.slippage_rate)


def create_commission_model(args: argparse.Namespace) -> CommissionModel:
    """Create the commission model selected by the CLI."""
    if args.commission_model == "none":
        return NoCommissionModel()
    if args.commission_model == "fixed":
        return FixedCommissionModel(commission=args.fixed_commission)
    if args.commission_model == "proportional":
        return ProportionalCommissionModel(percent=args.commission_rate)

    raise ValueError(f"Unknown commission model: {args.commission_model}.")


def create_data_source(args: argparse.Namespace) -> DataSource:
    """Create the historical data source selected by the CLI."""
    if args.source == "yfinance":
        return YFinanceDataSource()
    if args.source == "csv":
        if len(args.symbols) > 1 and args.csv_path.is_file():
            columns = normalize_column_names(pd.read_csv(args.csv_path, nrows=0)).columns
            if "symbol" not in columns:
                raise ValueError(
                    "A multi-symbol CSV file must contain a symbol column; "
                    "alternatively use a directory with SYMBOL.csv files."
                )
        return CSVDataSource(args.csv_path)

    raise ValueError(f"Unknown data source: {args.source}.")
