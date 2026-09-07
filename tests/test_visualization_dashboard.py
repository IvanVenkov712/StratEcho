from collections.abc import Iterator
from datetime import datetime, timedelta
from unittest.mock import Mock, call, patch

import matplotlib
import pytest

matplotlib.use("Agg")

from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import PercentFormatter

from backtester.domain.market import Candle
from backtester.domain.trading import PortfolioSnapshot, Side, Signal, Trade
from backtester.engine.backtest_result import BacktestRecord, BacktestResult
from backtester.visualization import dashboard


START = datetime(2026, 1, 1)


EMPTY_RESULT = BacktestResult(
    symbol="AAPL",
    initial_cash=1_000.0,
    records=[],
    trades=[],
    order_executions=[],
)


@pytest.fixture
def populated_result() -> BacktestResult:
    closes = [100.0, 105.0, 95.0, 100.0]
    values = [1_000.0, 1_025.0, 975.0, 1_000.0]
    cash_values = [1_000.0, 500.0, 500.0, 1_000.0]
    quantities = [0, 5, 5, 0]
    signals = [Signal.BUY, Signal.HOLD, Signal.SELL, Signal.HOLD]
    records = [
        BacktestRecord(
            frame=Candle(
                timestamp=START + timedelta(days=index),
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1_000,
            ),
            generated_signal=signal,
            snapshot=PortfolioSnapshot(
                cash=cash,
                value=value,
                positions={"AAPL": quantity} if quantity else {},
            ),
        )
        for index, (close, value, cash, quantity, signal) in enumerate(
            zip(closes, values, cash_values, quantities, signals, strict=True)
        )
    ]
    trades = [
        Trade("AAPL", Side.BUY, 5, 100.0, 0.0, START + timedelta(days=1)),
        Trade("AAPL", Side.SELL, 5, 100.0, 0.0, START + timedelta(days=3)),
    ]
    return BacktestResult(
        symbol="AAPL",
        initial_cash=1_000.0,
        records=records,
        trades=trades,
        order_executions=[],
    )


@pytest.fixture
def populated_figure(populated_result: BacktestResult) -> Iterator[Figure]:
    figure = dashboard.create_backtest_figure(populated_result)
    yield figure
    plt.close(figure)


def test_populate_price_panel_adds_prices_signals_trades_and_metadata() -> None:
    axes = Mock()

    with (
        patch.object(dashboard, "plot_close_prices") as plot_close_prices,
        patch.object(dashboard, "plot_signal_markers") as plot_signal_markers,
        patch.object(dashboard, "plot_trade_markers") as plot_trade_markers,
    ):
        dashboard.populate_price_panel(axes, EMPTY_RESULT)

    plot_close_prices.assert_called_once_with(axes, EMPTY_RESULT)
    assert plot_signal_markers.call_args_list == [
        call(axes, EMPTY_RESULT, Signal.BUY),
        call(axes, EMPTY_RESULT, Signal.SELL),
    ]
    assert plot_trade_markers.call_args_list == [
        call(axes, EMPTY_RESULT, Side.BUY),
        call(axes, EMPTY_RESULT, Side.SELL),
    ]
    axes.set_title.assert_called_once_with(label="Price")
    axes.legend.assert_called_once_with()


def test_populate_portfolio_panel_adds_portfolio_series_and_metadata() -> None:
    axes = Mock()

    with (
        patch.object(dashboard, "plot_equity") as plot_equity,
        patch.object(dashboard, "plot_cash") as plot_cash,
        patch.object(dashboard, "plot_market_value") as plot_market_value,
    ):
        dashboard.populate_portfolio_panel(axes, EMPTY_RESULT)

    plot_equity.assert_called_once_with(axes, EMPTY_RESULT)
    plot_cash.assert_called_once_with(axes, EMPTY_RESULT)
    plot_market_value.assert_called_once_with(axes, EMPTY_RESULT)
    axes.set_title.assert_called_once_with(label="Portfolio")
    axes.legend.assert_called_once_with()


def test_populate_position_panel_adds_quantity_and_metadata() -> None:
    axes = Mock()

    with patch.object(dashboard, "plot_position_quantity") as plot_quantity:
        dashboard.populate_position_panel(axes, EMPTY_RESULT)

    plot_quantity.assert_called_once_with(axes, EMPTY_RESULT)
    axes.set_title.assert_called_once_with(label="Position")
    axes.legend.assert_called_once_with()


def test_populate_risk_panel_adds_percentage_drawdown_and_metadata() -> None:
    axes = Mock()

    with patch.object(dashboard, "plot_drawdown") as plot_drawdown:
        dashboard.populate_risk_panel(axes, EMPTY_RESULT)

    plot_drawdown.assert_called_once_with(axes, EMPTY_RESULT)
    formatter = axes.yaxis.set_major_formatter.call_args.args[0]
    assert isinstance(formatter, PercentFormatter)
    assert formatter.xmax == 1.0
    axes.set_title.assert_called_once_with(label="Risk (Drawdown)")
    axes.legend.assert_called_once_with()


def test_create_backtest_figure_assembles_and_formats_shared_time_panels() -> None:
    figure = Mock()
    price_axes = Mock(name="price_axes")
    portfolio_axes = Mock(name="portfolio_axes")
    position_axes = Mock(name="position_axes")
    risk_axes = Mock(name="risk_axes")

    with (
        patch.object(
            dashboard.plt,
            "subplots",
            return_value=(
                figure,
                (price_axes, portfolio_axes, position_axes, risk_axes),
            ),
        ) as subplots,
        patch.object(dashboard, "populate_price_panel") as populate_price,
        patch.object(dashboard, "populate_portfolio_panel") as populate_portfolio,
        patch.object(dashboard, "populate_position_panel") as populate_position,
        patch.object(dashboard, "populate_risk_panel") as populate_risk,
    ):
        actual_figure = dashboard.create_backtest_figure(EMPTY_RESULT)

    subplots.assert_called_once_with(4, 1, figsize=(10, 20), sharex=True)
    populate_price.assert_called_once_with(price_axes, EMPTY_RESULT)
    populate_portfolio.assert_called_once_with(portfolio_axes, EMPTY_RESULT)
    populate_position.assert_called_once_with(position_axes, EMPTY_RESULT)
    populate_risk.assert_called_once_with(risk_axes, EMPTY_RESULT)
    figure.autofmt_xdate.assert_called_once_with()
    figure.tight_layout.assert_called_once_with()
    assert actual_figure is figure


def test_create_backtest_figure_adds_optional_dashboard_title() -> None:
    figure = dashboard.create_backtest_figure(
        EMPTY_RESULT,
        title="BuyAndHoldStrategy — AAPL",
    )

    try:
        assert figure._suptitle is not None
        assert figure._suptitle.get_text() == "BuyAndHoldStrategy — AAPL"
    finally:
        plt.close(figure)


def test_dashboard_title_does_not_overlap_price_panel_title() -> None:
    figure = dashboard.create_backtest_figure(
        EMPTY_RESULT,
        title="SimpleMovingAverageCrossStrategy(20, 50) - SPY",
    )

    try:
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        dashboard_title = figure._suptitle
        assert dashboard_title is not None

        dashboard_title_bounds = dashboard_title.get_window_extent(renderer)
        price_title_bounds = figure.axes[0].title.get_window_extent(renderer)

        assert price_title_bounds.y1 < dashboard_title_bounds.y0
    finally:
        plt.close(figure)


def test_created_figure_contains_expected_panels_artists_and_legends(
    populated_figure: Figure,
) -> None:
    price_axes, portfolio_axes, position_axes, risk_axes = populated_figure.axes

    assert [axes.get_title() for axes in populated_figure.axes] == [
        "Price",
        "Portfolio",
        "Position",
        "Risk (Drawdown)",
    ]
    assert [len(axes.lines) for axes in populated_figure.axes] == [1, 3, 1, 1]
    assert [len(axes.collections) for axes in populated_figure.axes] == [4, 0, 0, 0]
    assert _legend_labels(price_axes) == [
        "Close prices",
        "Signal Buy Markers",
        "Signal Sell Markers",
        "Trade markers for side Buy",
        "Trade markers for side Sell",
    ]
    assert _legend_labels(portfolio_axes) == [
        "Portfolio Equity",
        "Portfolio cash",
        "Market value",
    ]
    assert _legend_labels(position_axes) == ["Position quantity"]
    assert _legend_labels(risk_axes) == ["Portfolio drawdown"]
    assert isinstance(risk_axes.yaxis.get_major_formatter(), PercentFormatter)
    assert risk_axes.yaxis.get_major_formatter().xmax == 1.0


def test_created_figure_routes_each_series_to_the_correct_panel(
    populated_figure: Figure,
) -> None:
    price_axes, portfolio_axes, position_axes, risk_axes = populated_figure.axes

    assert list(price_axes.lines[0].get_ydata()) == pytest.approx(
        [100.0, 105.0, 95.0, 100.0]
    )
    assert list(portfolio_axes.lines[0].get_ydata()) == pytest.approx(
        [1_000.0, 1_025.0, 975.0, 1_000.0]
    )
    assert list(portfolio_axes.lines[1].get_ydata()) == pytest.approx(
        [1_000.0, 500.0, 500.0, 1_000.0]
    )
    assert list(portfolio_axes.lines[2].get_ydata()) == pytest.approx(
        [0.0, 525.0, 475.0, 0.0]
    )
    assert list(position_axes.lines[0].get_ydata()) == [0, 5, 5, 0]
    assert list(risk_axes.lines[0].get_ydata()) == pytest.approx(
        [0.0, 0.0, 975.0 / 1_025.0 - 1.0, 1_000.0 / 1_025.0 - 1.0]
    )


def test_created_figure_synchronizes_horizontal_limits_across_panels(
    populated_figure: Figure,
) -> None:
    price_axes, portfolio_axes, position_axes, risk_axes = populated_figure.axes

    portfolio_axes.set_xlim(10.0, 20.0)

    for axes in (price_axes, portfolio_axes, position_axes, risk_axes):
        assert axes.get_xlim() == pytest.approx((10.0, 20.0))


def test_create_backtest_figure_supports_an_empty_result() -> None:
    figure = dashboard.create_backtest_figure(EMPTY_RESULT)

    try:
        assert len(figure.axes) == 4
        assert [axes.get_title() for axes in figure.axes] == [
            "Price",
            "Portfolio",
            "Position",
            "Risk (Drawdown)",
        ]
        assert all(axes.get_legend() is not None for axes in figure.axes)
        assert all(
            len(line.get_ydata()) == 0
            for axes in figure.axes
            for line in axes.lines
        )
    finally:
        plt.close(figure)


def _legend_labels(axes: Axes) -> list[str]:
    legend = axes.get_legend()
    assert legend is not None
    return [text.get_text() for text in legend.get_texts()]
