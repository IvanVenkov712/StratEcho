"""Compare completed backtests using five time panels and an optional table."""

from collections.abc import Callable, Sequence
from datetime import datetime
from textwrap import fill

from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator, PercentFormatter

from backtester.engine.backtest_result import BacktestResult
from backtester.visualization.series import (
    cash_series,
    drawdown_series,
    equity_difference_series,
    equity_series,
    position_quantity_series,
)


def _validate_results(strategy: BacktestResult, benchmark: BacktestResult) -> None:
    """Require matching allocations and initial capital for a comparison."""
    if strategy.allocation != benchmark.allocation:
        raise ValueError("Comparison results must have the same symbols and allocations.")
    if strategy.initial_cash != benchmark.initial_cash:
        raise ValueError("Comparison results must have the same initial cash.")


def _format_heading(
    title: str,
    symbols: Sequence[str],
    timestamps: Sequence[datetime],
    subtitle: str | None,
) -> str:
    """Combine the comparison title, symbols, observation period, and subtitle."""
    period = (
        f"{timestamps[0]:%Y-%m-%d} through {timestamps[-1]:%Y-%m-%d}"
        if timestamps else "No observations"
    )
    heading = f"{fill(title, width=95)}\n{', '.join(symbols)} | {period}"
    if subtitle:
        heading += "\n" + "\n".join(fill(line, width=110) for line in subtitle.splitlines())
    return heading


def _create_axes(figure: Figure, metric_count: int) -> tuple[list[Axes], Axes | None]:
    """Create five panels sharing time and an optional separate table axis."""
    ratios = [2, 1, 1, 1, 1]
    if metric_count:
        ratios.append(max(1, 0.22 * (metric_count + 1)))
    grid = figure.add_gridspec(len(ratios), 1, height_ratios=ratios)
    equity_ax = figure.add_subplot(grid[0])
    axes = [equity_ax] + [
        figure.add_subplot(grid[index], sharex=equity_ax)
        for index in range(1, 5)
    ]
    table_ax = figure.add_subplot(grid[5]) if metric_count else None
    return axes, table_ax


def _plot_result_pair(
    axes: Axes,
    strategy: BacktestResult,
    benchmark: BacktestResult,
    transformer: Callable[[BacktestResult], tuple[list[datetime], list[float]]],
) -> None:
    """Plot the same series for both runs using consistent labels and styles."""
    for result, label, color, linestyle in (
        (strategy, "Strategy", "tab:blue", "-"),
        (benchmark, "Benchmark", "tab:orange", "--"),
    ):
        dates, values = transformer(result)
        axes.plot(dates, values, label=label, color=color, linestyle=linestyle)


def populate_equity_panel(
    axes: Axes, strategy: BacktestResult, benchmark: BacktestResult,
) -> None:
    """Compare portfolio equity in cash units with a legend."""
    _plot_result_pair(axes, strategy, benchmark, equity_series)
    axes.set_title("Portfolio equity")
    axes.set_ylabel("Cash units")
    axes.legend(loc="best")


def populate_drawdown_panel(
    axes: Axes, strategy: BacktestResult, benchmark: BacktestResult,
) -> None:
    """Compare each run's drawdown on a percentage-formatted axis."""
    _plot_result_pair(axes, strategy, benchmark, drawdown_series)
    axes.set_title("Drawdown")
    axes.set_ylabel("Drawdown (%)")
    axes.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))
    axes.legend(loc="best")


def populate_difference_panel(
    axes: Axes, timestamps: Sequence[datetime], differences: Sequence[float],
) -> None:
    """Plot precomputed equity differences with positive and negative shading."""
    axes.plot(timestamps, differences, color="tab:blue")
    axes.axhline(0, color="gray", linewidth=0.8)
    for positive, color in ((True, "tab:green"), (False, "tab:red")):
        axes.fill_between(
            timestamps, differences, 0,
            where=[value >= 0 if positive else value < 0 for value in differences],
            interpolate=True, color=color, alpha=0.15,
        )
    axes.set_title("Equity difference (strategy minus benchmark)")
    axes.set_ylabel("Cash units")


def populate_cash_panel(
    axes: Axes, strategy: BacktestResult, benchmark: BacktestResult,
) -> None:
    """Compare uninvested cash with a legend."""
    _plot_result_pair(axes, strategy, benchmark, cash_series)
    axes.set_title("Cash")
    axes.set_ylabel("Cash units")
    axes.legend(loc="best")


def populate_position_panel(
    axes: Axes, strategy: BacktestResult, benchmark: BacktestResult,
) -> None:
    """Compare held shares, using a shared color per symbol for multiple assets."""
    symbols = tuple(strategy.allocation.allocations)
    for index, symbol in enumerate(symbols):
        for result, label, linestyle in (
            (strategy, "Strategy", "-"), (benchmark, "Benchmark", "--"),
        ):
            dates, values = position_quantity_series(result, symbol)
            color = f"C{index % 10}"
            if len(symbols) == 1:
                color = "tab:blue" if label == "Strategy" else "tab:orange"
            axes.plot(dates, values, label=f"{label} {symbol}", color=color, linestyle=linestyle)
    axes.set_title("Position quantity")
    axes.set_ylabel("Shares")
    axes.yaxis.set_major_locator(MaxNLocator(integer=True))
    axes.legend(loc="best")


def _format_time_axes(axes: Sequence[Axes]) -> None:
    """Add panel grids and show date labels only below the last time panel."""
    for ax in axes:
        ax.grid(True, alpha=0.2)
    for ax in axes[:-1]:
        ax.tick_params(labelbottom=False)
    axes[-1].set_xlabel("Date")
    axes[-1].tick_params(axis="x", labelrotation=30)


def populate_metrics_table(
    axes: Axes, metric_rows: Sequence[tuple[str, str, str]],
) -> None:
    """Display preformatted metrics with a shaded header and left-aligned names."""
    axes.set_axis_off()
    table = axes.table(
        cellText=list(metric_rows),
        colLabels=["Metric", "Strategy", "Benchmark"],
        colWidths=[0.5, 0.25, 0.25],
        cellLoc="center", bbox=(0, 0, 1, 1),
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    for (row, column), cell in table.get_celld().items():
        cell.set_edgecolor("#dddddd")
        if row == 0:
            cell.set_facecolor("#eeeeee")
            cell.get_text().set_weight("bold")
        if column == 0:
            cell.get_text().set_ha("left")


def create_comparison_figure(
    strategy: BacktestResult,
    benchmark: BacktestResult,
    *,
    strategy_name: str = "Strategy",
    benchmark_name: str = "Benchmark",
    subtitle: str | None = None,
    metric_rows: Sequence[tuple[str, str, str]] = (),
) -> Figure:
    """Return equity, drawdown, difference, cash, and quantity comparisons.

    Results must share allocations, initial cash, and strictly ordered timestamps.
    Equity differences are absolute cash amounts, not percentage returns.
    Drawdowns use each result's own running equity peak. Values are recorded
    end-of-period snapshots, including the simulated costs of each run.

    Optional table rows contain preformatted (metric, strategy, benchmark)
    strings; callers supply already calculated metrics. The caller owns saving,
    displaying, and closing the returned figure. Two empty results are allowed.
    """
    _validate_results(strategy, benchmark)
    timestamps, differences = equity_difference_series(strategy, benchmark)
    heading = _format_heading(
        f"{strategy_name} vs {benchmark_name}",
        tuple(strategy.allocation.allocations),
        timestamps,
        subtitle,
    )

    figure = plt.figure(figsize=(12, 18), layout="constrained")
    try:
        axes, table_ax = _create_axes(figure, len(metric_rows))
        equity_ax, drawdown_ax, difference_ax, cash_ax, position_ax = axes
        populate_equity_panel(equity_ax, strategy, benchmark)
        populate_drawdown_panel(drawdown_ax, strategy, benchmark)
        populate_difference_panel(difference_ax, timestamps, differences)
        populate_cash_panel(cash_ax, strategy, benchmark)
        populate_position_panel(position_ax, strategy, benchmark)
        _format_time_axes(axes)
        if table_ax is not None:
            populate_metrics_table(table_ax, metric_rows)
        figure.suptitle(heading, fontsize=12)
    except Exception:
        plt.close(figure)
        raise
    return figure
