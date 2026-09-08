"""Resolve signal-time order intents into execution-time share quantities."""

from dataclasses import dataclass
from datetime import datetime

from backtester.execution.costs import ExecutionCostCalculator
from backtester.domain.trading import Side, SizingMode, SizingInstruction, Order, OrderIntent, PortfolioSnapshot
from backtester.sizing.asset_allocation import AssetAllocation


@dataclass(frozen=True)
class OrderResolutionContext:
    """Execution-time portfolio snapshot used to size an order intent."""

    timestamp: datetime
    reference_prices: dict[str, float]
    snapshot: PortfolioSnapshot
    allocation: AssetAllocation


@dataclass(frozen=True)
class QuantityResolutionContext:
    reference_price: float
    usable_cash: float
    current_quantity: int
    portfolio_value: float

    def __post_init__(self):
        if self.usable_cash < 0:
            raise ValueError("cash cannot be negative")

        if self.current_quantity < 0:
            raise ValueError("current quantity cannot be negative")

        if self.portfolio_value < self.usable_cash:
            raise ValueError("portfolio value cannot be less than cash")

        if self.reference_price <= 0:
            raise ValueError("price must be positive")


class BuyQuantityCapper:
    """Find the largest whole-share buy that fits an execution-cost budget."""

    def __init__(self, cost_calculator: ExecutionCostCalculator):
        self._cost_calculator: ExecutionCostCalculator = cost_calculator

    def cap(self, budget: float, reference_price: float, max_quantity: int | None = None) -> int:
        """Return an affordable quantity, optionally limited by ``max_quantity``.

        Affordability includes the configured buy slippage and commission. A
        zero result means that no positive whole-share quantity fits the budget.
        """

        quantity = int(budget // reference_price) + 1

        if max_quantity is not None:
            quantity = min(quantity, max_quantity)

        left = 1
        right = quantity

        while left <= right:
            middle = left + int((right - left) // 2)
            cost = self._cost_calculator.estimate_buy_cost(middle, reference_price)
            if cost > budget:
                right = middle - 1
            else:
                left = middle + 1

        return right

        # while quantity > 0 and self._cost_calculator.estimate_buy_cost(quantity, reference_price) > budget:
        #    quantity -= 1
        # return quantity


class QuantityResolver:
    """Resolve sizing instructions against an execution-time portfolio state.

    All-in, percent, and up-to buys are capped by estimated execution costs.
    Fixed buys retain their requested quantity and may therefore be rejected by
    the broker when unaffordable. Sell quantities never exceed the current
    position except in fixed mode, where the broker performs that validation.
    """

    def __init__(self, capper: BuyQuantityCapper):
        self._capper: BuyQuantityCapper = capper

    def resolve_quantity(self, side: Side, instr: SizingInstruction, context: QuantityResolutionContext) -> int:
        """Convert one side and sizing instruction into a whole-share quantity."""
        if side == Side.BUY:
            return self._resolve_buy_quantity(instr, context)
        elif side == Side.SELL:
            return self._resolve_sell_quantity(instr, context)
        else:
            raise ValueError("invalid side")

    def _resolve_affordable_quantity(
            self,
            budget: float,
            reference_price: float,
            max_quantity: int | None = None,
    ) -> int:
        return self._capper.cap(budget, reference_price, max_quantity)

    def _resolve_buy_quantity(self, instruction: SizingInstruction, context: QuantityResolutionContext) -> int:
        if instruction.mode == SizingMode.ALL_IN:
            return self._resolve_buy_quantity_all_in(context)
        elif instruction.mode == SizingMode.PERCENT:
            return self._resolve_buy_quantity_percent(instruction.value, context)
        elif instruction.mode == SizingMode.UP_TO:
            return self._resolve_buy_quantity_up_to(instruction.value, context)
        elif instruction.mode == SizingMode.FIXED:
            return self._resolve_buy_quantity_fixed(instruction.value, context)
        else:
            raise ValueError("Invalid sizing instruction")

    def _resolve_buy_quantity_all_in(self, context: QuantityResolutionContext) -> int:
        return self._resolve_affordable_quantity(
            context.usable_cash,
            context.reference_price,
        )

    def _resolve_buy_quantity_percent(self, percent: float, context: QuantityResolutionContext):
        budget = context.usable_cash * percent
        return self._resolve_affordable_quantity(budget, context.reference_price)

    def _resolve_buy_quantity_up_to(self, max_q: int, context: QuantityResolutionContext):
        return self._resolve_affordable_quantity(
            context.usable_cash,
            context.reference_price,
            max_q,
        )

    def _resolve_sell_quantity(self, instruction: SizingInstruction, context: QuantityResolutionContext) -> int:
        if instruction.mode == SizingMode.FIXED:
            return instruction.value
        elif instruction.mode == SizingMode.ALL_IN:
            return context.current_quantity
        elif instruction.mode == SizingMode.UP_TO:
            return min(instruction.value, context.current_quantity)
        elif instruction.mode == SizingMode.PERCENT:
            return int(context.current_quantity * instruction.value)
        else:
            raise ValueError("Invalid sizing instruction")

    def _resolve_buy_quantity_fixed(self, quantity: int, context: QuantityResolutionContext) -> int:
        max_affordable = self._capper.cap(context.usable_cash, context.reference_price)
        if quantity > max_affordable:
            return -1
        return quantity


class BufferQuantityResolver(QuantityResolver):
    """Cap requested buys so a configured fraction of cash remains reserved."""

    def __init__(self, resolver: QuantityResolver, capper: BuyQuantityCapper, buffer_rate: float):
        if not 0 <= buffer_rate < 1:
            raise ValueError("buffer_rate must be float in [0, 1)")
        self._resolver = resolver
        self._capper = capper
        self._buffer_rate = buffer_rate

    def resolve_quantity(self, side: Side, instr: SizingInstruction, context: QuantityResolutionContext) -> int:
        """Resolve a quantity and apply the cash buffer to positive buys only."""
        requested_quantity = self._resolver.resolve_quantity(side, instr, context)

        if side == Side.SELL or requested_quantity <= 0:
            return requested_quantity

        buffered_budget = context.usable_cash * (1 - self._buffer_rate)

        return self._capper.cap(
            budget=buffered_budget,
            reference_price=context.reference_price,
            max_quantity=requested_quantity,
        )


class OrderResolver:
    """Convert order intents into positive-quantity executable orders."""

    def __init__(self, q_resolver: QuantityResolver):
        self._q_resolver: QuantityResolver = q_resolver

    def resolve(self, intent: OrderIntent, context: OrderResolutionContext) -> Order | None:
        """Resolve ``intent`` while preserving signal and submission times.

        Return ``None`` when the resolved quantity is not positive.
        """
        usable_cash = context.snapshot.cash * context.allocation.allocations[intent.symbol]
        current_quantity = context.snapshot.positions.get(intent.symbol, 0)

        quantity_context = QuantityResolutionContext(
            usable_cash=usable_cash,
            current_quantity=current_quantity,
            portfolio_value=context.snapshot.value,
            reference_price=context.reference_prices[intent.symbol]
        )

        quantity = self._q_resolver.resolve_quantity(intent.side, intent.sizing_instruction, quantity_context)

        if quantity <= 0 or quantity is None:
            return None

        return Order(
            symbol=intent.symbol,
            side=intent.side,
            signal_timestamp=intent.timestamp,
            submitted_timestamp=context.timestamp,
            quantity=quantity
        )
