from datetime import datetime, timedelta
from dataclasses import replace

import pytest

from backtester.domain.market import Candle, MarketFrame
from backtester.domain.trading import PortfolioSnapshot, Side, Signal, Trade, MultiAssetSignal
from backtester.sizing.asset_allocation import AssetAllocation
from backtester.engine.backtest_result import BacktestRecord, BacktestResult
from backtester.visualization.series import (
    cash_series,
    close_price_series,
    drawdown_series,
    equity_series,
    equity_difference_series,
    market_value_series,
    position_quantity_series,
    signal_marker_series,
    trade_marker_series,
)


START = datetime(2026, 1, 1)


def test_equity_difference_preserves_sign_and_cash_units() -> None:
    timestamps = [START + timedelta(days=i) for i in range(3)]
    strategy = make_result([
        make_record(t, value=v, cash=v)
        for t, v in zip(timestamps, [1000, 1050, 950], strict=True)
    ])
    benchmark = make_result([
        make_record(t, value=1000, cash=1000) for t in timestamps
    ])
    assert equity_difference_series(strategy, benchmark) == (timestamps, [0, 50, -50])


@pytest.mark.parametrize("offsets", [[0], [0, 2], []])
def test_equity_difference_rejects_mismatched_timestamps(offsets: list[int]) -> None:
    strategy = make_result([
        make_record(START + timedelta(days=i), value=1000, cash=1000) for i in [0, 1]
    ])
    benchmark = make_result([
        make_record(START + timedelta(days=i), value=1000, cash=1000) for i in offsets
    ])
    with pytest.raises(ValueError, match="matching timestamps"):
        equity_difference_series(strategy, benchmark)


@pytest.mark.parametrize("offsets", [[1, 0], [0, 0]])
def test_equity_difference_rejects_unordered_or_duplicate_times(offsets: list[int]) -> None:
    result = make_result([
        make_record(START + timedelta(days=i), value=1000, cash=1000) for i in offsets
    ])
    with pytest.raises(ValueError, match="strictly increasing"):
        equity_difference_series(result, result)


def test_equity_difference_accepts_two_empty_results() -> None:
    assert equity_difference_series(make_result(), make_result()) == ([], [])


def make_candle(timestamp: datetime, close: float = 100.0) -> Candle:
    return Candle(
        timestamp=timestamp,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1_000,
    )


def make_record(
    timestamp: datetime,
    *,
    value: float,
    cash: float,
    close: float = 100.0,
    positions: dict[str, int] | None = None,
    signal: Signal = Signal.HOLD,
) -> BacktestRecord:
    return BacktestRecord(
        frame=MarketFrame(timestamp, {"AAPL": make_candle(timestamp, close=close)}),
        generated_signal=MultiAssetSignal({"AAPL": signal}),
        snapshot=PortfolioSnapshot(
            cash=cash,
            value=value,
            positions=positions or {},
        ),
    )


def make_result(
    records: list[BacktestRecord] | None = None,
    trades: list[Trade] | None = None,
) -> BacktestResult:
    return BacktestResult(
        allocation=AssetAllocation({"AAPL": 1.0}),
        initial_cash=1_000.0,
        records=records or [],
        trades=trades or [],
        order_executions=[],
    )


def test_close_price_series_returns_timestamps_and_closes_in_order() -> None:
    timestamps = [START, START + timedelta(days=1)]
    candles = [
        make_candle(timestamps[0], close=100.0),
        make_candle(timestamps[1], close=105.0),
    ]

    assert close_price_series(candles) == (timestamps, [100.0, 105.0])


def test_equity_series_returns_record_timestamps_and_values() -> None:
    timestamps = [START, START + timedelta(days=1)]
    result = make_result(
        [
            make_record(timestamps[0], value=1_000.0, cash=400.0),
            make_record(timestamps[1], value=1_050.0, cash=400.0),
        ]
    )

    assert equity_series(result) == (timestamps, [1_000.0, 1_050.0])


def test_cash_series_returns_record_timestamps_and_cash() -> None:
    timestamps = [START, START + timedelta(days=1)]
    result = make_result(
        [
            make_record(timestamps[0], value=1_000.0, cash=1_000.0),
            make_record(timestamps[1], value=1_050.0, cash=250.0),
        ]
    )

    assert cash_series(result) == (timestamps, [1_000.0, 250.0])


def test_drawdown_series_uses_running_portfolio_peak() -> None:
    values = [100.0, 120.0, 90.0, 135.0, 108.0]
    timestamps = [START + timedelta(days=index) for index in range(len(values))]
    result = make_result(
        [
            make_record(timestamp, value=value, cash=value)
            for timestamp, value in zip(timestamps, values)
        ]
    )

    actual_timestamps, drawdowns = drawdown_series(result)

    assert actual_timestamps == timestamps
    assert drawdowns == pytest.approx([0.0, 0.0, -0.25, 0.0, -0.20])


def test_drawdown_series_is_zero_when_running_peak_is_zero() -> None:
    result = make_result([make_record(START, value=0.0, cash=0.0)])

    assert drawdown_series(result) == ([START], [0.0])


def test_drawdown_series_returns_empty_lists_for_empty_result() -> None:
    assert drawdown_series(make_result()) == ([], [])


def test_trade_marker_series_filters_trades_by_side_and_preserves_order() -> None:
    first_buy_timestamp = START + timedelta(days=1)
    sell_timestamp = START + timedelta(days=2)
    second_buy_timestamp = START + timedelta(days=3)
    result = make_result(
        trades=[
            Trade("AAPL", Side.BUY, 2, 101.0, 0.0, first_buy_timestamp),
            Trade("AAPL", Side.SELL, 1, 104.0, 0.0, sell_timestamp),
            Trade("AAPL", Side.BUY, 1, 102.0, 0.0, second_buy_timestamp),
        ]
    )

    assert trade_marker_series(result, Side.BUY) == (
        [first_buy_timestamp, second_buy_timestamp],
        [101.0, 102.0],
    )


def test_trade_marker_series_returns_empty_lists_when_side_has_no_trades() -> None:
    assert trade_marker_series(make_result(), Side.SELL) == ([], [])


def test_position_quantity_series_uses_result_symbol_and_defaults_to_zero() -> None:
    timestamps = [START + timedelta(days=index) for index in range(3)]
    result = make_result(
        [
            make_record(timestamps[0], value=1_000.0, cash=1_000.0),
            make_record(
                timestamps[1],
                value=1_000.0,
                cash=700.0,
                positions={"AAPL": 3},
            ),
            make_record(
                timestamps[2],
                value=1_100.0,
                cash=900.0,
                positions={"AAPL": 1, "MSFT": 5},
            ),
        ]
    )

    assert position_quantity_series(result) == (timestamps, [0, 3, 1])


def test_market_value_series_returns_equity_minus_cash() -> None:
    timestamps = [START, START + timedelta(days=1)]
    result = make_result(
        [
            make_record(timestamps[0], value=1_000.0, cash=400.0),
            make_record(timestamps[1], value=1_050.0, cash=250.0),
        ]
    )

    assert market_value_series(result) == (timestamps, [600.0, 800.0])


def test_signal_marker_series_filters_signals_and_uses_candle_closes() -> None:
    timestamps = [START + timedelta(days=index) for index in range(4)]
    result = make_result(
        [
            make_record(
                timestamps[0],
                value=1_000.0,
                cash=1_000.0,
                close=101.0,
                signal=Signal.BUY,
            ),
            make_record(
                timestamps[1],
                value=1_000.0,
                cash=1_000.0,
                close=102.0,
                signal=Signal.HOLD,
            ),
            make_record(
                timestamps[2],
                value=1_010.0,
                cash=500.0,
                close=103.0,
                signal=Signal.BUY,
            ),
            make_record(
                timestamps[3],
                value=1_020.0,
                cash=500.0,
                close=104.0,
                signal=Signal.SELL,
            ),
        ]
    )

    assert signal_marker_series(result, Signal.BUY) == (
        [timestamps[0], timestamps[2]],
        [101.0, 103.0],
    )


def test_signal_marker_series_returns_empty_lists_when_signal_has_no_records() -> None:
    assert signal_marker_series(make_result(), Signal.SELL) == ([], [])


def test_multi_asset_series_keep_symbols_separate() -> None:
    record = BacktestRecord(
        frame=MarketFrame(START, {
            "AAPL": make_candle(START, close=100),
            "MSFT": make_candle(START, close=200),
        }),
        generated_signal=MultiAssetSignal({"AAPL": Signal.BUY, "MSFT": Signal.SELL}),
        snapshot=PortfolioSnapshot(cash=0, positions={"AAPL": 3, "MSFT": 4}, value=1100),
    )
    result = replace(
        make_result([record], [
            Trade("AAPL", Side.BUY, 3, 99, 0, START),
            Trade("MSFT", Side.BUY, 4, 199, 0, START),
        ]),
        allocation=AssetAllocation({"AAPL": 0.5, "MSFT": 0.5}),
    )
    assert signal_marker_series(result, Signal.BUY, "AAPL") == ([START], [100])
    assert signal_marker_series(result, Signal.BUY, "MSFT") == ([], [])
    assert signal_marker_series(result, Signal.SELL, "MSFT") == ([START], [200])
    assert trade_marker_series(result, Side.BUY, "MSFT") == ([START], [199])
    assert position_quantity_series(result, "AAPL") == ([START], [3])
    assert position_quantity_series(result, "MSFT") == ([START], [4])
    with pytest.raises(ValueError, match="Specify a symbol"):
        position_quantity_series(result)
