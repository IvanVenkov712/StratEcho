"""Export completed backtest dashboards to image files."""

from collections.abc import Sequence
from pathlib import Path

from matplotlib import pyplot as plt

from backtester.engine.backtest_result import BacktestResult
from backtester.visualization.dashboard import create_backtest_figure
from backtester.visualization.comparison import create_comparison_figure


def export_backtest_dashboard(
    result: BacktestResult,
    output_path: str | Path,
    *,
    title: str | None = None,
    dpi: int = 150,
    overwrite: bool = False,
) -> Path:
    """Create and save a backtest dashboard, then close its figure.

    The output format is inferred by Matplotlib from the file extension.
    """
    path = _prepare_output_path(output_path, dpi=dpi, overwrite=overwrite)

    figure = create_backtest_figure(result, title=title)
    try:
        figure.savefig(path, dpi=dpi, bbox_inches="tight")
    finally:
        plt.close(figure)

    return path


def export_comparison_dashboard(
    strategy: BacktestResult,
    benchmark: BacktestResult,
    output_path: str | Path,
    *,
    strategy_name: str = "Strategy",
    benchmark_name: str = "Benchmark",
    subtitle: str | None = None,
    metric_rows: Sequence[tuple[str, str, str]] = (),
    dpi: int = 150,
    overwrite: bool = False,
) -> Path:
    """Save a comparison dashboard, protecting existing files and closing it.

    Names, subtitle, and preformatted metric rows are passed to
    ``create_comparison_figure``. The file extension determines image format.
    """
    path = _prepare_output_path(output_path, dpi=dpi, overwrite=overwrite)
    figure = create_comparison_figure(
        strategy, benchmark,
        strategy_name=strategy_name,
        benchmark_name=benchmark_name,
        subtitle=subtitle,
        metric_rows=metric_rows,
    )
    try:
        figure.savefig(path, dpi=dpi, bbox_inches="tight")
    finally:
        plt.close(figure)
    return path


def _prepare_output_path(output_path: str | Path, *, dpi: int, overwrite: bool) -> Path:
    path = Path(output_path)

    if not path.suffix:
        raise ValueError("Output path must include a file extension.")

    if dpi <= 0:
        raise ValueError("dpi must be positive.")

    if path.exists() and not overwrite:
        raise FileExistsError(f"Output file already exists: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)

    return path
