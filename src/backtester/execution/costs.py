"""Slippage, commission, and estimated execution-cost models."""

from abc import ABC, abstractmethod
from math import isfinite
from numbers import Real

from backtester.domain.trading import Side


class ExecutionModel:
    """Apply symmetric adverse slippage to buy and sell reference prices."""

    def __init__(self, slippage_rate: float):
        if not 0 <= slippage_rate < 1:
            raise ValueError("slippage_rate must be in [0, 1)")

        self._slippage_rate = slippage_rate

    def calculate_fill_price(self, reference_price: float, side: Side) -> float:
        """Return a side-adjusted fill price for a positive reference price."""
        if reference_price <= 0:
            raise ValueError("reference_price must be positive")

        if side == Side.BUY:
            return reference_price * (1 + self._slippage_rate)
        elif side == Side.SELL:
            return reference_price * (1 - self._slippage_rate)
        else:
            raise ValueError("Unknown side")

class CommissionModel(ABC):
    """Interface for calculating a non-negative per-trade commission."""

    @abstractmethod
    def calculate(self, quantity: int, fill_price: float) -> float:
        """Return commission for a positive quantity and fill price."""
        pass

    def _validate(self, quantity: int, fill_price: float):
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if fill_price <= 0:
            raise ValueError("fill_price must be positive")


class NoCommissionModel(CommissionModel):
    """Validate trade inputs and charge no commission."""

    def calculate(self, quantity: int, fill_price: float) -> float:
        """Return zero commission for valid trade inputs."""
        self._validate(quantity, fill_price)
        return 0.0


class FixedCommissionModel(CommissionModel):
    """Charge the same configured cash amount for every trade."""

    _commission: float

    def __init__(self, commission: float):
        if not isinstance(commission, Real) or not isfinite(commission):
            raise ValueError("Commission must be a finite number.")
        if commission < 0:
            raise ValueError("Non-negative commission is required")
        self._commission = commission

    def calculate(self, quantity: int, fill_price: float) -> float:
        """Return the fixed commission after validating trade inputs."""
        self._validate(quantity, fill_price)
        return self._commission


class ProportionalCommissionModel(CommissionModel):
    """Charge a configured fraction of the trade notional."""

    _percent: float
    def __init__(self, percent: float):
        if not 0 <= percent <= 1:
            raise ValueError("percent must be between 0 and 1")
        self._percent = percent

    def calculate(self, quantity: int, fill_price: float) -> float:
        """Return ``quantity * fill_price * rate`` for valid inputs."""
        self._validate(quantity, fill_price)
        return quantity * fill_price * self._percent


class ExecutionCostCalculator:
    """Estimate cash requirements using the configured fill and fee models."""

    def __init__(self, execution_model: ExecutionModel, commission_model: CommissionModel):
        self._execution_model: ExecutionModel = execution_model
        self._commission_model: CommissionModel = commission_model

    def estimate_buy_cost(self, quantity: int, reference_price: float) -> float:
        """Return estimated buy notional plus commission after slippage."""
        fill_price = self._execution_model.calculate_fill_price(reference_price, Side.BUY)
        commission = self._commission_model.calculate(quantity, fill_price)
        return quantity * fill_price + commission

    def estimate_sell_cost(self, quantity: int, reference_price: float) -> float:
        """Return the commission charged for an estimated sell fill."""
        fill_price = self._execution_model.calculate_fill_price(reference_price,Side.SELL)
        commission = self._commission_model.calculate(quantity, fill_price)
        return commission
