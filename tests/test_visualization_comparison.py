from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import Mock

import matplotlib
import pytest

matplotlib.use("Agg")

from matplotlib import pyplot as plt
from matplotlib.ticker import PercentFormatter

from backtester.engine.backtest_result import BacktestResult
from backtester.sizing.asset_allocation import AssetAllocation
from backtester.visualization import comparison


RESULT = BacktestResult(AssetAllocation({"AAPL": 1.0}), 1000, [], [], [])


def test_comparison_routes_both_results_and_formats_five_panels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    benchmark = replace(RESULT)
    dates = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(3)]
    difference = Mock(return_value=(dates, [0, 50, -50]))
    monkeypatch.setattr(comparison, "equity_difference_series", difference)
    values_by_transformer = {
        "equity_series": ([1000, 1050, 950], [1000, 1000, 1000]),
        "drawdown_series": ([0, 0, -0.095238], [0, 0, 0]),
        "cash_series": ([1000, 500, 500], [1000, 0, 0]),
        "position_quantity_series": ([0, 5, 5], [0, 10, 10]),
    }
    transformers = []
    for name, (strategy_values, benchmark_values) in values_by_transformer.items():
        transformer = Mock(side_effect=[(dates, strategy_values), (dates, benchmark_values)])
        monkeypatch.setattr(comparison, name, transformer)
        transformers.append(transformer)
    figure = comparison.create_comparison_figure(
        RESULT, benchmark, strategy_name="Breakout", benchmark_name="Buy and Hold",
        subtitle="Strategy sizing: fixed shares\nBenchmark sizing: all in / all out",
        metric_rows=[("Total return", "-5.00%", "0.00%")],
    )
    try:
        figure.canvas.draw()
        equity, risk, difference_ax, cash, quantity, table_ax = figure.axes
        for ax, expected_values in zip(
            (equity, risk, cash, quantity), values_by_transformer.values(), strict=True,
        ):
            assert list(ax.lines[0].get_ydata()) == expected_values[0]
            assert list(ax.lines[1].get_ydata()) == expected_values[1]
            assert ax.lines[0].get_color() == "tab:blue"
            assert ax.lines[1].get_color() == "tab:orange"
            assert ax.lines[1].get_linestyle() == "--"
            assert ax.get_shared_x_axes().joined(ax, equity)
        assert isinstance(risk.yaxis.get_major_formatter(), PercentFormatter)
        assert list(difference_ax.lines[0].get_ydata()) == [0, 50, -50]
        assert len(difference_ax.collections) == 2
        assert equity.get_position().height > cash.get_position().height
        assert quantity.get_ylabel() == "Shares"
        assert table_ax.tables[0][1, 1].get_text().get_text() == "-5.00%"
        assert "Breakout vs Buy and Hold" in figure._suptitle.get_text()
        assert "2026-01-01 through 2026-01-03" in figure._suptitle.get_text()
        assert "Benchmark sizing: all in / all out" in figure._suptitle.get_text()
        difference.assert_called_once_with(RESULT, benchmark)
        for transformer in transformers:
            assert transformer.call_args_list[0].args[0] is RESULT
            assert transformer.call_args_list[1].args[0] is benchmark
    finally:
        plt.close(figure)


@pytest.mark.parametrize(
    ("benchmark", "message"),
    [(replace(RESULT, allocation=AssetAllocation({"MSFT": 1.0})), "same symbol"),
     (replace(RESULT, initial_cash=2000), "same initial cash")],
)
def test_comparison_rejects_incompatible_results(benchmark, message) -> None:
    with pytest.raises(ValueError, match=message):
        comparison.create_comparison_figure(RESULT, benchmark)


def test_comparison_can_render_empty_results_without_a_table() -> None:
    figure = comparison.create_comparison_figure(RESULT, RESULT)
    try:
        figure.canvas.draw()
        assert len(figure.axes) == 5
        assert "No observations" in figure._suptitle.get_text()
    finally:
        plt.close(figure)
