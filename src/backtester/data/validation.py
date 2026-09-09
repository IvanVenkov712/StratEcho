"""Validation helpers for chronological market data."""

from itertools import pairwise
from typing import Collection, Sequence

from backtester.domain.market import Candle, MarketFrame


def validate_symbols(
    symbols: Collection[str],
    supported_symbols: Collection[str],
    *,
    source: str,
    require_all: bool = True,
) -> None:
    """Reject unsupported symbols and, by default, missing supported symbols."""
    actual = set(symbols)
    supported = set(supported_symbols)
    unsupported = actual - supported
    missing = supported - actual if require_all else set()
    if unsupported or missing:
        raise ValueError(
            f"{source} symbols do not match supported symbols: "
            f"unsupported={sorted(unsupported)!r}, missing={sorted(missing)!r}."
        )


def validate_candles_chronological(candles: Sequence[Candle]) -> None:
    """Require candle timestamps to be unique and strictly increasing."""

    for previous, current in pairwise(candles):
        try:
            is_chronological = previous.timestamp < current.timestamp
        except TypeError as exc:
            raise ValueError(
                "Candle timestamps must be comparable and strictly increasing."
            ) from exc

        if not is_chronological:
            raise ValueError(
                "Candle timestamps must be comparable and strictly increasing."
            )

def validate_frames_chronological(frames: Sequence[MarketFrame]) -> None:
    """Require candle timestamps to be unique and strictly increasing."""

    for previous, current in pairwise(frames):
        try:
            is_chronological = previous.timestamp < current.timestamp
        except TypeError as exc:
            raise ValueError(
                "Candle timestamps must be comparable and strictly increasing."
            ) from exc

        if not is_chronological:
            raise ValueError(
                "Candle timestamps must be comparable and strictly increasing."
            )
