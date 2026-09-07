"""Long-only cash, position, and mark-to-market portfolio accounting."""

from collections.abc import Mapping
from math import isfinite
from numbers import Real

from backtester.domain.trading import PortfolioSnapshot
from backtester.sizing.asset_allocation import AssetAllocation


class Portfolio:
    """Tracks long-only cash and positions for a backtest portfolio."""

    def __init__(self, cash: float, positions: Mapping[str, int] | None = None):
        self._cash = 0.0
        self._positions: dict[str, int] = {}

        self.cash = cash
        for symbol, quantity in (positions or {}).items():
            self._validate_symbol(symbol)
            self._validate_quantity(quantity, "Position quantity")
            self._positions[symbol] = quantity

    @property
    def cash(self) -> float:
        """Return the portfolio's uninvested cash."""
        return self._cash

    @cash.setter
    def cash(self, value: float) -> None:
        """Set cash to a finite, non-negative value."""
        self._validate_cash(value)
        self._cash = float(value)

    @property
    def positions(self) -> dict[str, int]:
        """Return a copy of symbol-to-whole-share positions."""
        return self._positions.copy()

    def position_quantity(self, symbol: str) -> int:
        """Return the owned quantity for ``symbol``, or zero when absent."""
        self._validate_symbol(symbol)
        return self._positions.get(symbol, 0)

    def add_position(self, symbol: str, quantity: int) -> None:
        """Add a positive whole-share quantity to a position."""
        self._validate_symbol(symbol)
        self._validate_quantity(quantity, "Position quantity")
        self._positions[symbol] = self.position_quantity(symbol) + quantity

    def remove_position(self, symbol: str, quantity: int) -> None:
        """Remove owned shares, deleting the position when it reaches zero."""
        self._validate_symbol(symbol)
        self._validate_quantity(quantity, "Position quantity")

        owned = self.position_quantity(symbol)
        if quantity > owned:
            raise ValueError("Cannot remove more shares than the portfolio owns.")

        remaining = owned - quantity
        if remaining == 0:
            del self._positions[symbol]
        else:
            self._positions[symbol] = remaining

    def value(self, prices: Mapping[str, float], strict: bool = True) -> float:
        """Return cash plus the market value of every open position."""
        total = self.cash
        for symbol, quantity in self._positions.items():
            if symbol not in prices and strict:
                raise ValueError(f"Missing market price for position: {symbol}.")

            price = prices.get(symbol, 0)
            self._validate_price(price)
            total += float(price) * quantity

        return total

    def snapshot(self, prices: Mapping[str, float], strict: bool = True) -> PortfolioSnapshot:
        """Capture cash, total value, and a copy of current positions."""
        return PortfolioSnapshot(
            value=self.value(prices, strict),
            cash=self.cash,
            positions=self.positions
        )

    def available_cash_for_assets(self, allocation: AssetAllocation) -> dict[str, float]:
        return {
            symbol: self.cash * weight
            for symbol, (weight, _) in allocation.allocations.items()
        }

    @staticmethod
    def _validate_cash(value: float) -> None:
        if not isinstance(value, Real) or not isfinite(value):
            raise ValueError("Cash must be a finite number.")

        if value < 0:
            raise ValueError("Cash must not be negative.")

    @staticmethod
    def _validate_price(value: float) -> None:
        if not isinstance(value, Real) or not isfinite(value):
            raise ValueError("Market price must be a finite number.")

        if value < 0:
            raise ValueError("Market price must be non-negative.")

    @staticmethod
    def _validate_quantity(value: int, label: str) -> None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{label} must be an integer.")

        if value <= 0:
            raise ValueError(f"{label} must be positive.")

    @staticmethod
    def _validate_symbol(symbol: str) -> None:
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("Symbol must be a non-empty string.")
