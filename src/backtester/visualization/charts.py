"""Composable Matplotlib layers for visualizing backtest results.

Each function adds a line or marker collection to a caller-supplied ``Axes``.
The caller owns chart-level formatting such as titles, axis labels, grids, and
legends, as well as displaying or saving the containing figure.
"""

from datetime import datetime
from typing import Callable

from matplotlib.axes import Axes

from backtester.domain.trading import Side, Signal
from backtester.engine.backtest_result import BacktestResult
from backtester.visualization.series import (
    cash_series,
    close_price_series,
    drawdown_series,
    equity_series,
    market_value_series,
    position_quantity_series,
    signal_marker_series,
    trade_marker_series,
)


def plot_series(
    axes: Axes,
    result: BacktestResult,
    series_transformer: Callable[
        [BacktestResult],
        tuple[list[datetime], list[float | int]],
    ],
    *,
    label: str,
    color: str,
) -> None:
    """Add a transformed backtest series to ``axes`` as a colored line.

    ``label`` identifies the line when the caller later creates a legend. This
    function deliberately leaves all chart-level axes metadata unchanged.
    """
    timestamps, values = series_transformer(result)

    axes.plot(
        timestamps,
        values,
        label=label,
        color=color,
    )


def plot_markers(
    axes: Axes,
    result: BacktestResult,
    series_transformer: Callable[
        [BacktestResult],
        tuple[list[datetime], list[float | int]],
    ],
    *,
    label: str,
    color: str,
    marker: str,
    filled: bool,
) -> None:
    """Add transformed backtest points to ``axes`` as scatter markers.

    Filled markers represent executed trades, while hollow markers distinguish
    strategy signals. The caller remains responsible for axes metadata and for
    creating the legend.
    """
    timestamps, values = series_transformer(result)

    axes.scatter(
        timestamps,
        values,
        marker=marker,
        label=label,
        s=60,
        zorder=3,
        color=color if filled else "none",
        edgecolors=color,
        linewidths=1.5,
    )


def plot_close_prices(axes: Axes, result: BacktestResult) -> None:
    """Plot a separate closing-price line for each symbol."""
    for index, symbol in enumerate(result.allocation.allocations):
        timestamps, values = close_price_series([
            record.frame.candles[symbol] for record in result.records
        ])
        label = _symbol_label("Close prices", result, symbol)
        color = "tab:cyan" if len(result.allocation.allocations) == 1 else f"C{index % 10}"
        axes.plot(timestamps, values, label=label, color=color)

def plot_equity(axes: Axes, result: BacktestResult) -> None:
    """Plot total portfolio equity over time."""
    plot_series(axes, result, equity_series, label="Portfolio Equity", color="tab:blue")

def plot_cash(axes: Axes, result: BacktestResult) -> None:
    """Plot uninvested portfolio cash over time."""
    plot_series(axes, result, cash_series, label="Portfolio cash", color="tab:green")

def plot_drawdown(axes: Axes, result: BacktestResult) -> None:
    """Plot fractional drawdown from the running portfolio-equity peak."""
    plot_series(axes, result, drawdown_series, label="Portfolio drawdown", color="tab:red")



def plot_trade_markers(
    axes: Axes, result: BacktestResult, side: Side, symbol: str | None = None,
) -> None:
    """Plot filled markers at fill times and prices for trades on ``side``."""
    if symbol is None:
        for asset in result.allocation.allocations:
            plot_trade_markers(axes, result, side, asset)
        return
    marker_by_side = {
        Side.BUY: "^",
        Side.SELL: "v"
    }
    color_by_side = {
        Side.BUY: "tab:green",
        Side.SELL: "tab:blue",
    }
    
    transformer = lambda result: trade_marker_series(result, side, symbol)
    label = _symbol_label(f"Trade markers for side {side.value.title()}", result, symbol)

    plot_markers(
        axes, 
        result, 
        transformer, 
        label=label,
        color=color_by_side[side],
        marker=marker_by_side[side],
        filled=True,
    )
    
    

def plot_position_quantity(axes: Axes, result: BacktestResult) -> None:
    """Plot held shares separately for each symbol."""
    for index, symbol in enumerate(result.allocation.allocations):
        timestamps, values = position_quantity_series(result, symbol)
        label = _symbol_label("Position quantity", result, symbol)
        color = "tab:brown" if len(result.allocation.allocations) == 1 else f"C{index % 10}"
        axes.plot(timestamps, values, label=label, color=color)

def plot_market_value(axes: Axes, result: BacktestResult) -> None:
    """Plot invested market value, defined as total equity minus cash."""
    plot_series(axes, result, market_value_series, label="Market value", color="tab:gray")

def plot_signal_markers(
    axes: Axes, result: BacktestResult, signal: Signal, symbol: str | None = None,
) -> None:
    """Plot hollow markers where ``signal`` became known at candle close.

    The marker price is the signal candle's close, not the fill price of any
    resulting trade. Under the engine's timing model, that trade normally
    executes at the next candle's open.
    """
    if symbol is None:
        for asset in result.allocation.allocations:
            plot_signal_markers(axes, result, signal, asset)
        return
    marker_by_signal = {
        Signal.BUY: "^",
        Signal.SELL: "v",
        Signal.HOLD: "o",
    }
    
    color_by_signal = {
        Signal.BUY: "tab:green",
        Signal.SELL: "tab:blue",
        Signal.HOLD: "tab:gray"
    }
    title = _symbol_label(f"Signal {signal.value.title()} Markers", result, symbol)

    transformer = lambda result: signal_marker_series(result, signal, symbol)
    plot_markers(
        axes, 
        result, 
        transformer, 
        label=title,
        color=color_by_signal[signal],
        marker=marker_by_signal[signal],
        filled=False,
    )


def _symbol_label(label: str, result: BacktestResult, symbol: str) -> str:
    return f"{label} ({symbol})" if len(result.allocation.allocations) > 1 else label
