from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from backtester.data.frames import market_frames_from_candles
from backtester.domain.market import Candle, MarketFrame


def candles_at_days(*days: int, price: float = 100) -> list[Candle]:
    return [
        Candle(
            timestamp=datetime(2026, 1, day),
            open=price,
            high=price,
            low=price,
            close=price,
            volume=1_000,
        )
        for day in days
    ]


def test_combines_all_symbols_and_preserves_original_candles() -> None:
    aapl = candles_at_days(2, 5, price=100)
    msft = tuple(candles_at_days(2, 5, price=200))

    frames = market_frames_from_candles({"AAPL": aapl, "MSFT": msft})

    assert frames == [
        MarketFrame(datetime(2026, 1, 2), {"AAPL": aapl[0], "MSFT": msft[0]}),
        MarketFrame(datetime(2026, 1, 5), {"AAPL": aapl[1], "MSFT": msft[1]}),
    ]
    assert frames[0].candles["AAPL"] is aapl[0]
    assert frames[1].candles["MSFT"] is msft[1]
    assert frames[0].close_prices() == {"AAPL": 100, "MSFT": 200}
    assert aapl == candles_at_days(2, 5, price=100)


def test_accepts_a_single_symbol_and_single_candle() -> None:
    candles = candles_at_days(2)

    assert market_frames_from_candles({"AAPL": candles}) == [
        MarketFrame(datetime(2026, 1, 2), {"AAPL": candles[0]})
    ]


@pytest.mark.parametrize("data", [{}, {"AAPL": []}, {"AAPL": [], "MSFT": ()}])
def test_empty_input_returns_no_frames(data: dict[str, Sequence[Candle]]) -> None:
    assert market_frames_from_candles(data) == []


@pytest.mark.parametrize(
    "days",
    [(), (2, 3), (3, 4), (2, 4), (2, 3, 4, 5), (2, 3, 5)],
    ids=["empty", "missing-end", "missing-start", "gap", "extra", "shifted"],
)
@pytest.mark.parametrize("reverse_symbols", [False, True])
def test_rejects_mismatched_timestamps(
    days: tuple[int, ...], reverse_symbols: bool,
) -> None:
    data = {"AAPL": candles_at_days(2, 3, 4), "MSFT": candles_at_days(*days)}
    if reverse_symbols:
        data = dict(reversed(list(data.items())))

    with pytest.raises(ValueError, match="Timestamps .* must match"):
        market_frames_from_candles(data)


@pytest.mark.parametrize("days", [(2, 2), (3, 2)], ids=["duplicate", "descending"])
@pytest.mark.parametrize("symbol", ["AAPL", "MSFT"])
def test_rejects_non_chronological_candles(
    days: tuple[int, ...], symbol: str,
) -> None:
    data = {"AAPL": candles_at_days(2, 3), "MSFT": candles_at_days(2, 3)}
    data[symbol] = candles_at_days(*days)

    with pytest.raises(ValueError, match=f"{symbol!r}.*strictly increasing"):
        market_frames_from_candles(data)


def test_rejects_mixed_naive_and_aware_timestamps_within_a_symbol() -> None:
    candles = candles_at_days(2, 3)
    candles[1] = replace(
        candles[1], timestamp=candles[1].timestamp.replace(tzinfo=timezone.utc)
    )

    with pytest.raises(ValueError, match="AAPL.*comparable and strictly increasing"):
        market_frames_from_candles({"AAPL": candles})


def test_rejects_naive_and_aware_timestamps_across_symbols() -> None:
    candle = candles_at_days(2)[0]
    aware = replace(candle, timestamp=candle.timestamp.replace(tzinfo=timezone.utc))

    with pytest.raises(ValueError, match="Timestamps .* must match"):
        market_frames_from_candles({"AAPL": [candle], "MSFT": [aware]})


def test_matches_aware_timestamps_representing_the_same_instant() -> None:
    candle = candles_at_days(2)[0]
    utc_candle = replace(candle, timestamp=candle.timestamp.replace(tzinfo=timezone.utc))
    local_candle = replace(
        candle,
        timestamp=utc_candle.timestamp.astimezone(timezone(timedelta(hours=2))),
    )

    assert market_frames_from_candles({"AAPL": [utc_candle], "MSFT": [local_candle]}) == [
        MarketFrame(utc_candle.timestamp, {"AAPL": utc_candle, "MSFT": local_candle})
    ]
