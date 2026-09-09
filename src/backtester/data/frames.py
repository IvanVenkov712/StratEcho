"""Combine aligned per-symbol candles into chronological market frames."""

from collections.abc import Mapping, Sequence

from backtester.data.validation import validate_candles_chronological
from backtester.domain.market import Candle, MarketFrame


def market_frames_from_candles(
    candles_by_symbol: Mapping[str, Sequence[Candle]],
) -> list[MarketFrame]:
    """Require identical, strictly increasing timestamps across all symbols.

    Return one frame per timestamp, retaining the original candles. Raise
    ``ValueError`` for unordered or duplicate timestamps and missing or extra
    bars in any symbol. No sorting, filling, or intersection is performed.
    Dates absent from every symbol are allowed: no calendar is inferred.
    An empty mapping or exclusively empty sequences returns an empty list.
    """
    if not candles_by_symbol:
        return []

    reference_symbol = next(iter(candles_by_symbol))
    reference_candles = candles_by_symbol[reference_symbol]

    for symbol, candles in candles_by_symbol.items():
        try:
            validate_candles_chronological(candles)
        except ValueError as exc:
            raise ValueError(f"Invalid candles for {symbol!r}: {exc}") from exc

        if len(candles) != len(reference_candles):
            raise ValueError(
                f"Timestamps for {symbol!r} must match {reference_symbol!r}: "
                f"expected {len(reference_candles)} candles, got {len(candles)}."
            )

        for reference, candle in zip(reference_candles, candles, strict=True):
            if candle.timestamp != reference.timestamp:
                raise ValueError(
                    f"Timestamps for {symbol!r} must match {reference_symbol!r}: "
                    f"expected {reference.timestamp!r}, got {candle.timestamp!r}."
                )

    return [
        MarketFrame(
            timestamp=reference.timestamp,
            candles={
                symbol: candles[index]
                for symbol, candles in candles_by_symbol.items()
            },
        )
        for index, reference in enumerate(reference_candles)
    ]
