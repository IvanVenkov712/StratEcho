"""Validated market-data domain models."""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from numbers import Real
from typing import Mapping


@dataclass(frozen=True)
class Candle:
    """Immutable, validated OHLCV observation for one trading period."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime):
            raise ValueError("Candle timestamp must be a datetime.")

        for name in ("open", "high", "low", "close"):
            price = getattr(self, name)
            if not isinstance(price, Real) or isinstance(price, bool) or not isfinite(price):
                raise ValueError(f"Candle {name} price must be a finite number.")

            if price <= 0:
                raise ValueError(f"Candle {name} price must be positive.")

        if (
            not isinstance(self.volume, Real)
            or isinstance(self.volume, bool)
            or not isfinite(self.volume)
        ):
            raise ValueError("Candle volume must be a finite number.")

        if self.volume < 0:
            raise ValueError("Candle volume must not be negative.")

        if self.high < self.low:
            raise ValueError("Candle high must be greater than or equal to low.")

        if not self.low <= self.open <= self.high:
            raise ValueError("Candle open price must be between low and high.")

        if not self.low <= self.close <= self.high:
            raise ValueError("Candle close price must be between low and high.")


@dataclass(frozen=True)
class MarketFrame:
    timestamp: datetime
    candles: Mapping[str, Candle]

    def __post_init__(self):
        for candle in self.candles.values():
            if candle.timestamp != self.timestamp:
                raise ValueError("All candles should have the same timestamp equal to self.timestamp")