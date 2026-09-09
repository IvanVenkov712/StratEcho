"""Compare completed backtests using five time panels and an optional table."""

from collections.abc import Sequence
from textwrap import fill

from matplotlib import pyplot as plt
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
    if strategy.allocation != benchmark.allocation:
        raise ValueError("Comparison results must have the same symbols and allocations.")
    if strategy.initial_cash != benchmark.initial_cash:
        raise ValueError("Comparison results must have the same initial cash.")
    timestamps, differences = equity_difference_series(strategy, benchmark)

    heading = f"{strategy_name} vs {benchmark_name}"
    period = (
        f"{timestamps[0]:%Y-%m-%d} through {timestamps[-1]:%Y-%m-%d}"
        if timestamps else "No observations"
    )
    symbols = tuple(strategy.allocation.allocations)
    heading = f"{fill(heading, width=95)}\n{', '.join(symbols)} | {period}"
    if subtitle:
        heading += "\n" + "\n".join(fill(line, width=110) for line in subtitle.splitlines())

    figure = plt.figure(figsize=(12, 18), layout="constrained")
    try:
        ratios = [2, 1, 1, 1, 1]
        if metric_rows:
            ratios.append(max(1, 0.22 * (len(metric_rows) + 1)))
        grid = figure.add_gridspec(len(ratios), 1, height_ratios=ratios)
        equity_ax = figure.add_subplot(grid[0])
        axes = [equity_ax] + [
            figure.add_subplot(grid[index], sharex=equity_ax)
            for index in range(1, 5)
        ]
        panels = (
            (axes[0], equity_series, "Portfolio equity", "Cash units"),
            (axes[1], drawdown_series, "Drawdown", "Drawdown (%)"),
            (axes[3], cash_series, "Cash", "Cash units"),
        )
        for ax, transformer, title, ylabel in panels:
            for result, label, color, linestyle in (
                (strategy, "Strategy", "tab:blue", "-"),
                (benchmark, "Benchmark", "tab:orange", "--"),
            ):
                dates, values = transformer(result)
                ax.plot(dates, values, label=label, color=color, linestyle=linestyle)
            ax.set_title(title)
            ax.set_ylabel(ylabel)
            ax.legend(loc="best")

        for index, symbol in enumerate(symbols):
            for result, label, linestyle in (
                (strategy, "Strategy", "-"), (benchmark, "Benchmark", "--"),
            ):
                dates, values = position_quantity_series(result, symbol)
                color = f"C{index % 10}"
                if len(symbols) == 1:
                    color = "tab:blue" if label == "Strategy" else "tab:orange"
                axes[4].plot(dates, values, label=f"{label} {symbol}", color=color, linestyle=linestyle)
        axes[4].set_title("Position quantity")
        axes[4].set_ylabel("Shares")
        axes[4].legend(loc="best")

        axes[1].yaxis.set_major_formatter(PercentFormatter(xmax=1.0))
        axes[4].yaxis.set_major_locator(MaxNLocator(integer=True))
        difference_ax = axes[2]
        difference_ax.plot(timestamps, differences, color="tab:blue")
        difference_ax.axhline(0, color="gray", linewidth=0.8)
        for positive, color in ((True, "tab:green"), (False, "tab:red")):
            difference_ax.fill_between(
                timestamps, differences, 0,
                where=[value >= 0 if positive else value < 0 for value in differences],
                interpolate=True, color=color, alpha=0.15,
            )
        difference_ax.set_title("Equity difference (strategy minus benchmark)")
        difference_ax.set_ylabel("Cash units")
        for ax in axes:
            ax.grid(True, alpha=0.2)
        for ax in axes[:-1]:
            ax.tick_params(labelbottom=False)
        axes[-1].set_xlabel("Date")
        axes[-1].tick_params(axis="x", labelrotation=30)

        if metric_rows:
            table_ax = figure.add_subplot(grid[5])
            table_ax.set_axis_off()
            table = table_ax.table(
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
        figure.suptitle(heading, fontsize=12)
    except Exception:
        plt.close(figure)
        raise
    return figure
