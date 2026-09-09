from datetime import datetime
from math import inf

import pytest

from backtester.domain.market import Candle
from backtester.domain.trading import MultiAssetSignal, Signal

TIMESTAMP = datetime(2026, 1, 1)


def test_multi_asset_signals_preserve_history_when_strategy_reuses_dictionary() -> None:
    signals = {"AAPL": Signal.BUY}
    first = MultiAssetSignal(signals)
    signals["AAPL"] = Signal.HOLD
    second = MultiAssetSignal(signals)
    signals.clear()

    assert first.signals == {"AAPL": Signal.BUY}
    assert second.signals == {"AAPL": Signal.HOLD}


def test_multi_asset_signal_mapping_cannot_be_modified() -> None:
    signal = MultiAssetSignal({"AAPL": Signal.BUY})

    with pytest.raises(TypeError):
        signal.signals["AAPL"] = Signal.HOLD


def make_candle(**overrides: object) -> Candle:
    values = {
        "timestamp": TIMESTAMP,
        "open": 100,
        "high": 110,
        "low": 90,
        "close": 105,
        "volume": 1_000,
    }
    values.update(overrides)

    return Candle(**values)


def test_candle_accepts_valid_ohlcv_values() -> None:
    candle = make_candle()

    assert candle.open == 100
    assert candle.high == 110
    assert candle.low == 90
    assert candle.close == 105
    assert candle.volume == 1_000


@pytest.mark.parametrize("field", ["open", "high", "low", "close"])
def test_candle_rejects_non_positive_prices(field: str) -> None:
    with pytest.raises(ValueError, match=f"Candle {field} price must be positive"):
        make_candle(**{field: 0})


def test_candle_rejects_non_finite_price() -> None:
    with pytest.raises(ValueError, match="Candle close price must be a finite number"):
        make_candle(close=inf)


def test_candle_rejects_negative_volume() -> None:
    with pytest.raises(ValueError, match="Candle volume must not be negative"):
        make_candle(volume=-1)


def test_candle_rejects_high_below_low() -> None:
    with pytest.raises(ValueError, match="high must be greater than or equal to low"):
        make_candle(high=89, low=90)


def test_candle_rejects_open_outside_high_low_range() -> None:
    with pytest.raises(ValueError, match="open price must be between low and high"):
        make_candle(open=111)


def test_candle_rejects_close_outside_high_low_range() -> None:
    with pytest.raises(ValueError, match="close price must be between low and high"):
        make_candle(close=89)
