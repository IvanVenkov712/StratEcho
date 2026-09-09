"""Declarative buy and sell sizing policy."""

from dataclasses import dataclass

from backtester.domain.trading import SizingInstruction, Side


@dataclass(frozen=True)
class SizingPlan:
    """Pair the sizing instructions used for buy and sell signals."""

    buy: SizingInstruction
    sell: SizingInstruction

    def instruction_for(self, side: Side) -> SizingInstruction:
        """Return the instruction configured for ``side``."""
        if side == Side.BUY:
            return self.buy
        elif side == Side.SELL:
            return self.sell
        else:
            raise ValueError("invalid side")

@dataclass(frozen=True)
class MultiAssetSizingPlan:
    plans: dict[str, SizingPlan]