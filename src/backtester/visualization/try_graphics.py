"""Display the local MSFT RSI demo dashboard.

Run with ``python -m backtester.visualization.try_graphics`` after installing
the project in editable mode. Data comes from the repository's data/MSFT.csv.
"""

from matplotlib import pyplot as plt

from backtester.visualization.dashboard import create_backtest_figure
from backtester.visualization.sample_data import load_results


def main() -> None:
    """Run the sample backtest and display prices, portfolio, position, and risk."""
    results = load_results()
    create_backtest_figure(results, title="MSFT - Wilder RSI (14), thresholds 30/70")
    plt.show()


if __name__ == "__main__":
    main()
