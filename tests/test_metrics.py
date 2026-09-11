from datetime import datetime, timedelta
from math import isclose, sqrt

import pytest

from backtester.domain.market import Candle, MarketFrame
from backtester.domain.trading import PortfolioSnapshot, Side, Signal, Trade, MultiAssetSignal
from backtester.sizing.asset_allocation import AssetAllocation
from backtester.engine.backtest_result import BacktestRecord, BacktestResult
from backtester.metrics.metrics import (
    MetricData,
    PerformanceAnalyzer,
    annual_sharpe_ratio,
    annual_volatility,
    annualized_return,
    daily_avg,
    daily_sharpe_ratio,
    daily_volatility,
    max_drawdown,
    number_of_trades,
    period_returns,
    total_return,
)


def make_record(timestamp: datetime, portfolio_value: float) -> BacktestRecord:
    candle_price = 100.0
    return BacktestRecord(
        frame=MarketFrame(timestamp, {"AAPL": Candle(
            timestamp=timestamp,
            open=candle_price,
            high=candle_price,
            low=candle_price,
            close=candle_price,
            volume=1_000,
        )}),
        generated_decision=MultiAssetSignal({"AAPL": Signal.HOLD}),
        snapshot=PortfolioSnapshot(
            cash=portfolio_value,
            value=portfolio_value,
            positions={},
        ),
    )


def make_result(
    values: list[float],
    *,
    start: datetime = datetime(2026, 1, 1),
    trades: list[Trade] | None = None,
) -> BacktestResult:
    records = [
        make_record(start + timedelta(days=index), value)
        for index, value in enumerate(values)
    ]

    return BacktestResult(
        allocation=AssetAllocation({"AAPL": 1.0}),
        initial_cash=values[0] if values else 0.0,
        records=records,
        trades=trades or [],
        order_executions=[],
    )


def test_total_return_uses_first_and_last_portfolio_values() -> None:
    result = make_result([1_000, 1_100, 1_250])

    assert total_return(result) == 0.25


@pytest.mark.parametrize(
    "metric",
    [total_return, annualized_return, max_drawdown],
)
def test_record_based_metrics_are_zero_for_empty_result(metric) -> None:
    result = make_result([])

    assert metric(result) == 0


def test_annualized_return_uses_elapsed_calendar_days() -> None:
    result = make_result(
        [100, 121],
        start=datetime(2026, 1, 1),
    )
    result = BacktestResult(
        allocation=result.allocation,
        initial_cash=result.initial_cash,
        records=[
            result.records[0],
            make_record(datetime(2027, 1, 1), 121),
        ],
        trades=[],
        order_executions=[],
    )

    expected = (121 / 100) ** (365.25 / 365) - 1

    assert isclose(annualized_return(result), expected)


def test_annualized_return_is_zero_with_only_one_record() -> None:
    result = make_result([100])

    assert annualized_return(result) == 0


def test_period_returns_are_simple_returns_between_consecutive_records() -> None:
    result = make_result([100, 120, 108])

    assert period_returns(result) == pytest.approx([0.2, -0.1])


def test_period_returns_are_zero_after_portfolio_equity_reaches_zero() -> None:
    result = make_result([100, 0, 0])

    assert period_returns(result) == pytest.approx([-1, 0])


def test_daily_average_is_mean_of_period_returns() -> None:
    result = make_result([100, 120, 108])

    assert daily_avg(result) == pytest.approx(0.05)


def test_daily_average_is_zero_when_no_period_returns_exist() -> None:
    result = make_result([100])

    assert daily_avg(result) == 0


def test_daily_volatility_uses_sample_standard_deviation() -> None:
    result = make_result([100, 120, 108])

    assert daily_volatility(result) == pytest.approx(sqrt(0.045))


def test_daily_volatility_is_zero_with_fewer_than_two_period_returns() -> None:
    result = make_result([100, 110])

    assert daily_volatility(result) == 0


def test_annual_volatility_scales_daily_volatility_by_trading_days() -> None:
    result = make_result([100, 120, 108])

    assert annual_volatility(result) == pytest.approx(sqrt(0.045) * sqrt(252))


def test_max_drawdown_returns_largest_peak_to_trough_loss() -> None:
    result = make_result([100, 120, 90, 135, 108])

    assert max_drawdown(result) == pytest.approx(-0.25)


def test_max_drawdown_is_zero_when_portfolio_never_falls_below_peak() -> None:
    result = make_result([100, 110, 120])

    assert max_drawdown(result) == 0


def test_sharpe_ratios_use_average_return_divided_by_volatility() -> None:
    result = make_result([100, 120, 108])
    expected_daily_sharpe = 0.05 / sqrt(0.045)

    assert daily_sharpe_ratio(result) == pytest.approx(expected_daily_sharpe)
    assert annual_sharpe_ratio(result) == pytest.approx(
        expected_daily_sharpe * sqrt(252)
    )


def test_number_of_trades_counts_recorded_trades() -> None:
    trades = [
        Trade(
            "AAPL",
            Side.BUY,
            quantity=10,
            fill_price=20,
            commission=1.0,
            timestamp=datetime(2026, 1, 2),
        ),
        Trade(
            "AAPL",
            Side.SELL,
            quantity=4,
            fill_price=25,
            commission=1.0,
            timestamp=datetime(2026, 1, 3),
        ),
    ]
    result = make_result([1_000], trades=trades)

    assert number_of_trades(result) == 2


def test_performance_analyzer_calculates_registered_metrics() -> None:
    result = make_result([100, 125])
    analyzer = PerformanceAnalyzer()
    analyzer.add_metric_func("total_return", "Total return", total_return)
    analyzer.add_metric_func("trades", "Number of trades", number_of_trades)

    assert analyzer.calculate_metrics(result) == {
        "total_return": MetricData("Total return", 0.25),
        "trades": MetricData("Number of trades", 0),
    }


def test_performance_analyzer_rejects_duplicate_metric_names() -> None:
    analyzer = PerformanceAnalyzer()
    analyzer.add_metric_func("total_return", "Total return", total_return)

    with pytest.raises(ValueError, match="metric name must be unique"):
        analyzer.add_metric_func("total_return", "Duplicate", total_return)
