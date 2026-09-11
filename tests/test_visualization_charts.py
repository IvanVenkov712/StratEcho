from collections.abc import Callable, Iterator
from datetime import datetime, timedelta

import numpy as np
import pytest
from matplotlib import dates as mdates
from matplotlib.axes import Axes
from matplotlib.colors import to_rgba
from matplotlib.figure import Figure
from matplotlib.markers import MarkerStyle
from matplotlib.path import Path as MatplotlibPath

from backtester.domain.trading import SignalDecision
from backtester.domain.market import Candle, MarketFrame
from backtester.domain.trading import PortfolioSnapshot, Side, Signal, Trade, MultiAssetSignal
from backtester.engine.backtest_result import BacktestRecord, BacktestResult
from backtester.visualization.charts import (
    plot_cash,
    plot_close_prices,
    plot_drawdown,
    plot_equity,
    plot_market_value,
    plot_position_quantity,
    plot_signal_markers,
    plot_trade_markers,
)


START = datetime(2026, 1, 1)


def make_record(
    timestamp: datetime,
    *,
    close: float,
    value: float,
    cash: float,
    quantity: int,
    signal: Signal,
) -> BacktestRecord:
    candle = Candle(
        timestamp=timestamp,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1_000,
    )
    positions = {"AAPL": quantity} if quantity else {}
    snapshot = PortfolioSnapshot(cash=cash, value=value, positions=positions)
    return BacktestRecord(MarketFrame(timestamp, {"AAPL": candle}), SignalDecision(timestamp, MultiAssetSignal({"AAPL": signal})), snapshot)


@pytest.fixture
def axes() -> Iterator[Axes]:
    figure = Figure()
    axes = figure.subplots()
    yield axes
    figure.clear()


@pytest.fixture
def result() -> BacktestResult:
    records = [
        make_record(
            START,
            close=100.0,
            value=1_000.0,
            cash=1_000.0,
            quantity=0,
            signal=Signal.BUY,
        ),
        make_record(
            START + timedelta(days=1),
            close=105.0,
            value=950.0,
            cash=425.0,
            quantity=5,
            signal=Signal.HOLD,
        ),
        make_record(
            START + timedelta(days=2),
            close=110.0,
            value=900.0,
            cash=900.0,
            quantity=0,
            signal=Signal.SELL,
        ),
    ]
    trades = [
        Trade("AAPL", Side.BUY, 5, 101.0, 0.0, START + timedelta(hours=12)),
        Trade(
            "AAPL",
            Side.SELL,
            5,
            109.0,
            0.0,
            START + timedelta(days=1, hours=12),
        ),
    ]
    return BacktestResult(
        symbols=("AAPL",),
        initial_cash=1_000.0,
        records=records,
        trades=trades,
        order_executions=[],
    )


@pytest.mark.parametrize(
    ("plotter", "expected_values", "expected_label", "expected_color"),
    [
        (plot_close_prices, [100.0, 105.0, 110.0], "Close prices", "tab:cyan"),
        (plot_equity, [1_000.0, 950.0, 900.0], "Portfolio Equity", "tab:blue"),
        (plot_cash, [1_000.0, 425.0, 900.0], "Portfolio cash", "tab:green"),
        (plot_drawdown, [0.0, -0.05, -0.1], "Portfolio drawdown", "tab:red"),
        (plot_position_quantity, [0, 5, 0], "Position quantity", "tab:brown"),
        (plot_market_value, [0.0, 525.0, 0.0], "Market value", "tab:gray"),
    ],
)
def test_line_plotters_add_the_expected_line(
    axes: Axes,
    result: BacktestResult,
    plotter: Callable[[Axes, BacktestResult], None],
    expected_values: list[float | int],
    expected_label: str,
    expected_color: str,
) -> None:
    plotter(axes, result)

    assert len(axes.lines) == 1
    line = axes.lines[0]
    assert list(line.get_xdata()) == [record.timestamp for record in result.records]
    assert list(line.get_ydata()) == pytest.approx(expected_values)
    assert line.get_label() == expected_label
    assert line.get_color() == expected_color


@pytest.mark.parametrize(
    ("side", "timestamp", "price", "label", "color", "marker"),
    [
        (
            Side.BUY,
            START + timedelta(hours=12),
            101.0,
            "Trade markers for side Buy",
            "tab:green",
            "^",
        ),
        (
            Side.SELL,
            START + timedelta(days=1, hours=12),
            109.0,
            "Trade markers for side Sell",
            "tab:blue",
            "v",
        ),
    ],
)
def test_trade_marker_plotters_add_filled_markers(
    axes: Axes,
    result: BacktestResult,
    side: Side,
    timestamp: datetime,
    price: float,
    label: str,
    color: str,
    marker: str,
) -> None:
    plot_trade_markers(axes, result, side)

    assert len(axes.collections) == 1
    collection = axes.collections[0]
    assert collection.get_label() == label
    assert_marker_data(collection.get_offsets(), [timestamp], [price])
    assert_marker_shape(collection.get_paths()[0], marker)
    np.testing.assert_allclose(collection.get_facecolors(), [to_rgba(color)])
    np.testing.assert_allclose(collection.get_edgecolors(), [to_rgba(color)])


@pytest.mark.parametrize(
    ("signal", "timestamp", "price", "label", "color", "marker"),
    [
        (Signal.BUY, START, 100.0, "Signal Buy Markers", "tab:green", "^"),
        (
            Signal.HOLD,
            START + timedelta(days=1),
            105.0,
            "Signal Hold Markers",
            "tab:gray",
            "o",
        ),
        (
            Signal.SELL,
            START + timedelta(days=2),
            110.0,
            "Signal Sell Markers",
            "tab:blue",
            "v",
        ),
    ],
)
def test_signal_marker_plotters_add_hollow_markers(
    axes: Axes,
    result: BacktestResult,
    signal: Signal,
    timestamp: datetime,
    price: float,
    label: str,
    color: str,
    marker: str,
) -> None:
    plot_signal_markers(axes, result, signal)

    assert len(axes.collections) == 1
    collection = axes.collections[0]
    assert collection.get_label() == label
    assert_marker_data(collection.get_offsets(), [timestamp], [price])
    assert_marker_shape(collection.get_paths()[0], marker)
    assert collection.get_facecolors().size == 0
    np.testing.assert_allclose(collection.get_edgecolors(), [to_rgba(color)])


def test_plotters_do_not_overwrite_existing_axes_metadata(
    axes: Axes,
    result: BacktestResult,
) -> None:
    axes.set_title("Price and executions")
    axes.set_ylabel("Price")

    plot_close_prices(axes, result)
    plot_trade_markers(axes, result, Side.BUY)
    plot_signal_markers(axes, result, Signal.BUY)

    assert axes.get_title() == "Price and executions"
    assert axes.get_ylabel() == "Price"


def assert_marker_data(
    offsets: np.ma.MaskedArray,
    timestamps: list[datetime],
    values: list[float],
) -> None:
    np.testing.assert_allclose(offsets[:, 0], mdates.date2num(timestamps))
    np.testing.assert_allclose(offsets[:, 1], values)


def assert_marker_shape(actual_path: MatplotlibPath, marker: str) -> None:
    marker_style = MarkerStyle(marker)
    expected_path = marker_style.get_path().transformed(marker_style.get_transform())
    np.testing.assert_allclose(actual_path.vertices, expected_path.vertices)
    if expected_path.codes is None:
        assert actual_path.codes is None
    else:
        np.testing.assert_array_equal(actual_path.codes, expected_path.codes)
