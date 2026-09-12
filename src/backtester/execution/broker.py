"""Long-only broker execution and portfolio-accounting service."""

from datetime import datetime
from typing import List

from backtester.exceptions.trading_errors import (
    PriceNotFoundError,
    InsufficientFundsError,
    InsufficientPositionError,
)
from backtester.execution.costs import CommissionModel, ExecutionModel, fits_budget
from backtester.portfolio.portfolio import Portfolio
from backtester.domain.trading import Side, Trade, Order, OrderExecutionResult, OrderExecutionStatus


class Broker:
    """Execute validated orders and apply successful fills to a portfolio."""

    _portfolio: Portfolio
    _execution_model: ExecutionModel
    _commission_model: CommissionModel

    def __init__(self, portfolio: Portfolio,
                 execution_model: ExecutionModel,
                 commission_model: CommissionModel
        ):
        self._portfolio = portfolio
        self._execution_model = execution_model
        self._commission_model = commission_model

    @property
    def portfolio(self) -> Portfolio:
        """Return the portfolio maintained by this broker."""
        return self._portfolio

    def _buy(self, order: Order, fill_price: float, commission: float) -> None:
        if fill_price <= 0:
            raise ValueError("Price must be positive.")

        cost = fill_price * order.quantity + commission
        if not fits_budget(cost, self._portfolio.cash):
            raise InsufficientFundsError

        remaining_cash = self._portfolio.cash - cost
        self._portfolio.cash = max(0.0, remaining_cash)
        self._portfolio.add_position(order.symbol, order.quantity)

    def _sell(self, order: Order, fill_price: float, commission: float):
        if fill_price <= 0:
            raise ValueError("Price must be positive.")

        owned = self._portfolio.position_quantity(order.symbol)

        if order.quantity > owned:
            raise InsufficientPositionError

        new_budget = self._portfolio.cash + order.quantity * fill_price
        if not fits_budget(commission, new_budget):
            raise InsufficientFundsError("Not enough cash for the commission")

        new_cash = new_budget - commission
        self._portfolio.cash = max(0, new_cash)
        self._portfolio.remove_position(order.symbol, order.quantity)

    def _execute_internal(self, order: Order, prices: dict[str, float], timestamp: datetime) -> Trade:
        """Execute an order using the supplied reference price and timestamp.

        Slippage is applied to the reference price before commission and
        portfolio updates are calculated. Rejected orders do not change the
        portfolio and do not produce a trade.
        Execution may occur at submission time or later, never before it.
        """
        if not order.symbol in prices:
            raise PriceNotFoundError

        _validate_timestamp(timestamp=timestamp)
        if timestamp < order.submitted_timestamp:
            raise ValueError("Execution timestamp cannot precede order submission.")

        fill_price = self._execution_model.calculate_fill_price(prices[order.symbol], order.side)
        commission = self._commission_model.calculate(order.quantity, fill_price)

        trade = Trade(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
            commission=commission,
            timestamp=timestamp
        )

        if order.side == Side.BUY:
            self._buy(order, fill_price, commission)
        elif order.side == Side.SELL:
            self._sell(order, fill_price, commission)
        else:
            raise ValueError("Invalid order side")

        return trade

    def execute(self, order: Order, prices: dict[str, float], timestamp: datetime) -> OrderExecutionResult:
        trade = None
        try:
            trade = self._execute_internal(order, prices, timestamp)
        except InsufficientFundsError:
            status = OrderExecutionStatus.INSUFFICIENT_FUNDS
        except InsufficientPositionError:
            status = OrderExecutionStatus.INSUFFICIENT_POSITION
        else:
            status = OrderExecutionStatus.SUCCESS

        return OrderExecutionResult(
            status=status,
            order=order,
            trade=trade,
        )


def _validate_timestamp(timestamp: datetime) -> None:
    if not isinstance(timestamp, datetime):
        raise ValueError("Timestamp must be a datetime.")
