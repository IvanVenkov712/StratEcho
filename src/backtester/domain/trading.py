"""Trading signals, sizing instructions, orders, and fills."""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from math import isfinite
from numbers import Real
from types import MappingProxyType

class Signal(Enum):
    """Action proposed by a strategy after observing available candles."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"

class Side(Enum):
    """Direction of an order or executed trade."""

    BUY = "buy"
    SELL = "sell"

class SizingMode(Enum):
    """Rule used to translate an order intent into a share quantity."""

    FIXED = auto()
    PERCENT = auto()
    ALL_IN = auto()
    UP_TO = auto()

class OrderExecutionStatus(Enum):
    SUCCESS = "success"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    INSUFFICIENT_POSITION = "insufficient_position"
    PRICE_NOT_FOUND = "price_not_found"
    VALIDATION_ERROR = "validation_error"
    UNKNOWN_ERROR = "unknown_error"

@dataclass(frozen=True)
class MultiAssetSignal:
    """Immutable copy of per-symbol signals at one observation."""

    signals: Mapping[str, Signal]

    def __post_init__(self) -> None:
        object.__setattr__(self, "signals", MappingProxyType(dict(self.signals)))

@dataclass(frozen=True)
class SizingInstruction:
    """Sizing mode and its validated parameter, when the mode requires one."""

    value: int | float | None
    mode: SizingMode

    def __post_init__(self):
        if self.mode == SizingMode.FIXED or self.mode == SizingMode.UP_TO:
            _validate_quantity(self.value)
        elif self.mode == SizingMode.PERCENT:
            _validate_percent(self.value)
        elif self.mode == SizingMode.ALL_IN:
            if self.value is not None:
                raise ValueError("With all in value should be none")
        else:
            raise ValueError("correct sizing mode expected")

@dataclass(frozen=True)
class OrderIntent:
    """Unsized request timestamped when its strategy signal became known."""

    symbol: str
    side: Side
    timestamp: datetime
    sizing_instruction: SizingInstruction

    def __post_init__(self) -> None:
        _validate_symbol(self.symbol)
        _validate_side(self.side)
        _validate_timestamp(self.timestamp)

@dataclass(frozen=True)
class Order:
    """Sized request retaining its signal and submission timestamps.

    ``signal_timestamp`` records when the strategy signal became known.
    ``submitted_timestamp`` records when the intent was resolved and submitted
    for execution, and therefore cannot precede the signal timestamp.
    """

    symbol: str
    side: Side
    quantity: int
    signal_timestamp: datetime
    submitted_timestamp: datetime

    def __post_init__(self) -> None:
        _validate_symbol(self.symbol)
        _validate_side(self.side)
        _validate_quantity(self.quantity)
        _validate_timestamp(self.submitted_timestamp)
        _validate_timestamp(self.signal_timestamp)
        if self.signal_timestamp > self.submitted_timestamp:
            raise ValueError("signal_timestamp cannot be after submitted_timestamp")

@dataclass(frozen=True)
class Trade:
    """Immutable fill whose timestamp records successful execution time."""

    symbol: str
    side: Side
    quantity: int
    fill_price: float
    commission: float
    timestamp: datetime

    def __post_init__(self) -> None:
        _validate_symbol(self.symbol)
        _validate_side(self.side)
        _validate_quantity(self.quantity)
        _validate_price(self.fill_price)
        _validate_commission(self.commission)
        _validate_timestamp(self.timestamp)

@dataclass(frozen = True)
class OrderExecutionResult:
    status: OrderExecutionStatus
    order: Order
    trade: Trade | None

    def __post_init__(self):
        if self.status is not OrderExecutionStatus.SUCCESS and self.trade is not None:
            raise ValueError("Unsuccessful order execution should not lead to a trade")

        if self.status is OrderExecutionStatus.SUCCESS and self.trade is None:
            raise ValueError("Successful order execution should lead to a trade")


@dataclass(frozen=True)
class TargetAllocation:
    timestamp: datetime
    weights: Mapping[str, float]

    def __post_init__(self):
        _validate_timestamp(self.timestamp)
        _validate_weights(self.weights)

class PendingDecision:
    pass

@dataclass(frozen=True)
class SignalDecision(PendingDecision):
    intents: tuple[OrderIntent, ...]


@dataclass(frozen=True)
class RebalanceDecision(PendingDecision):
    target: TargetAllocation

@dataclass(frozen=True)
class PortfolioSnapshot:
    """Point-in-time cash, total equity, and detached position quantities."""

    cash: float
    value: float
    positions: dict[str, int]

def _validate_symbol(symbol: str) -> None:
    if not isinstance(symbol, str) or not symbol:
        raise ValueError("Symbol must be a non-empty string.")


def _validate_side(side: Side) -> None:
    if not isinstance(side, Side):
        raise ValueError("Side must be a Side.")

def _validate_quantity(quantity: int) -> None:
    if not isinstance(quantity, int) or isinstance(quantity, bool):
        raise ValueError("Quantity must be an integer.")

    if quantity <= 0:
        raise ValueError("Quantity must be positive.")

def _validate_quantity_instruction(instr: float) -> None:
    if not isinstance(instr, float):
        raise ValueError("The instruction must be a float")

    if not 0 <= instr <= 1:
        raise ValueError("The instruction muse be between 0 and 1")


def _validate_price(price: float) -> None:
    if not isinstance(price, Real) or not isfinite(price):
        raise ValueError("Price must be a finite number.")

    if price <= 0:
        raise ValueError("Price must be positive.")

def _validate_percent(value):
    if not (isinstance(value, float | int) and 0 <= value <= 1) or isinstance(value, bool):
        raise ValueError("value must be in [0, 1]")

def _validate_commission(commission: float) -> None:
    if not isinstance(commission, Real) or not isfinite(commission):
        raise ValueError("Price must be a finite number.")

    if commission < 0:
        raise ValueError("Commission must be non-negative.")


def _validate_timestamp(timestamp: datetime) -> None:
    if not isinstance(timestamp, datetime):
        raise ValueError("Timestamp must be a datetime.")

def _validate_weights(weights: Mapping[str, float]):
    if any(not 0 <= weight <= 1 for weight in weights.values()):
        raise ValueError("All weights must be in [0, 1]")

    if sum(weight for weight in weights.values()) > 1:
        raise ValueError("Weights sum must be <= 1")
