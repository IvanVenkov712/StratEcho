"""Convert backtest data into timestamped values for visualization."""

from datetime import datetime
from math import isclose
from typing import Sequence

from backtester.domain.market import Candle
from backtester.domain.trading import Side, Signal
from backtester.engine.backtest_result import BacktestResult


def close_price_series(
    candles: Sequence[Candle],
) -> tuple[list[datetime], list[float]]:
    """Return candle timestamps and closing prices in input order."""
    return (
        [candle.timestamp for candle in candles],
        [candle.close for candle in candles]
    )


def equity_series(
    result: BacktestResult,
) -> tuple[list[datetime], list[float]]:
    """Return record timestamps and total portfolio equity in record order."""
    return (
        [record.timestamp for record in result.records],
        [record.snapshot.value for record in result.records]
    )


def equity_difference_series(
    strategy: BacktestResult,
    benchmark: BacktestResult,
) -> tuple[list[datetime], list[float]]:
    """Return strategy minus benchmark equity in cash units at matching times.

    Observations must match exactly and be strictly chronological. No alignment,
    interpolation, or filling is performed, including for unequal lengths.
    """
    timestamps, strategy_values = equity_series(strategy)
    benchmark_timestamps, benchmark_values = equity_series(benchmark)
    if timestamps != benchmark_timestamps:
        raise ValueError("Comparison results must have matching timestamps.")
    if any(later <= earlier for earlier, later in zip(timestamps, timestamps[1:])):
        raise ValueError("Comparison timestamps must be strictly increasing.")
    return timestamps, [
        value - benchmark_value
        for value, benchmark_value in zip(strategy_values, benchmark_values, strict=True)
    ]


def cash_series(
    result: BacktestResult,
) -> tuple[list[datetime], list[float]]:
    """Return record timestamps and uninvested portfolio cash in record order."""
    return (
        [record.timestamp for record in result.records],
        [record.snapshot.cash for record in result.records]
    )


def drawdown_series(
    result: BacktestResult,
) -> tuple[list[datetime], list[float]]:
    """Return fractional drawdown from the running peak at each record.

    Drawdown is calculated as ``value / running_peak - 1``. A zero running
    peak produces a drawdown of ``0.0`` because no percentage loss can be
    measured from a zero-valued portfolio.
    """

    if not result.records:
        return [], []
    curr_max = float("-inf")
    drawdowns = []
    timestamps = []
    for r in result.records:
        v = r.snapshot.value
        if v > curr_max:
            curr_max = v
        if isclose(curr_max, 0):
            drawdowns.append(0.0)
        else:
            drawdowns.append(v / curr_max - 1)
        timestamps.append(r.frame.timestamp)

    return timestamps, drawdowns


def trade_marker_series(
    result: BacktestResult,
    side: Side,
    symbol: str | None = None,
) -> tuple[list[datetime], list[float]]:
    """Return fill timestamps and prices for trades matching ``side``."""
    return (
        [trade.timestamp for trade in result.trades if trade.side == side and (symbol is None or trade.symbol == symbol)],
        [trade.fill_price for trade in result.trades if trade.side == side and (symbol is None or trade.symbol == symbol)],
    )


def position_quantity_series(
    result: BacktestResult,
    symbol: str | None = None,
) -> tuple[list[datetime], list[int]]:
    """Return held quantities for one symbol, defaulting to a singleton universe.

    Records without an open position for the selected symbol have quantity zero.
    """
    symbol = _resolve_symbol(result, symbol)
    return (
        [record.timestamp for record in result.records],
        [
            record.snapshot.positions.get(symbol, 0)
            for record in result.records
        ],
    )


def market_value_series(
    result: BacktestResult,
) -> tuple[list[datetime], list[float]]:
    """Return timestamps and invested market value in record order.

    Market value is total portfolio equity minus uninvested cash.
    """
    return (
        [record.timestamp for record in result.records],
        [record.market_value for record in result.records],
    )


def signal_marker_series(
    result: BacktestResult,
    signal: Signal,
    symbol: str | None = None,
) -> tuple[list[datetime], list[float]]:
    """Return timestamps and closing prices for records matching ``signal``.

    The closing price locates the signal where it became known. It is not an
    execution price; a resulting trade normally executes at the next candle's
    open according to the backtest engine's timing model.
    """
    symbol = _resolve_symbol(result, symbol)
    matching_records = [
        record
        for record in result.records
        if record.generated_signal.signals.get(symbol) == signal
    ]

    return (
        [record.timestamp for record in matching_records],
        [record.frame.candles[symbol].close for record in matching_records],
    )


def _resolve_symbol(result: BacktestResult, symbol: str | None) -> str:
    if symbol is None:
        if len(result.allocation.allocations) != 1:
            raise ValueError("Specify a symbol for a multi-asset series.")
        return next(iter(result.allocation.allocations))
    if symbol not in result.allocation.allocations:
        raise ValueError(f"Unknown result symbol: {symbol}.")
    return symbol
