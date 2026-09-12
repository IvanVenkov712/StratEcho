from datetime import datetime
from unittest.mock import Mock

import pytest

from backtester.execution.broker import Broker
from backtester.execution.costs import CommissionModel, ExecutionModel
from backtester.exceptions.trading_errors import PriceNotFoundError
from backtester.domain.trading import (
    Order,
    OrderExecutionResult,
    OrderExecutionStatus,
    Side,
    Trade,
)

SIGNAL_TIMESTAMP = datetime(2026, 1, 1, 9, 29)
ORDER_TIMESTAMP = datetime(2026, 1, 1, 9, 30)
EXECUTION_TIMESTAMP = datetime(2026, 1, 1, 9, 31)


def make_order(symbol: str, side: Side, quantity: int) -> Order:
    return Order(
        symbol=symbol,
        side=side,
        quantity=quantity,
        signal_timestamp=SIGNAL_TIMESTAMP,
        submitted_timestamp=ORDER_TIMESTAMP,
    )


def make_portfolio_mock(cash: float = 1_000, owned_quantity: int = 0) -> Mock:
    portfolio = Mock()
    portfolio.cash = cash
    portfolio.position_quantity.return_value = owned_quantity
    return portfolio


def make_broker(
    portfolio: Mock,
    fill_price: float = 20.0,
    commission: float = 2.0,
) -> tuple[Broker, Mock, Mock]:
    execution_model = Mock(spec=ExecutionModel)
    execution_model.calculate_fill_price.return_value = fill_price

    commission_model = Mock(spec=CommissionModel)
    commission_model.calculate.return_value = commission

    broker = Broker(portfolio, execution_model, commission_model)
    return broker, execution_model, commission_model


def execute_order(
    broker: Broker,
    order: Order,
    price: float,
    timestamp: datetime = EXECUTION_TIMESTAMP,
) -> OrderExecutionResult:
    return broker.execute(order, prices={order.symbol: price}, timestamp=timestamp)


def test_buy_order_uses_models_updates_portfolio_and_returns_trade() -> None:
    portfolio = make_portfolio_mock(cash=1_000)
    broker, execution_model, commission_model = make_broker(
        portfolio,
        fill_price=20.0,
        commission=2.0,
    )
    order = make_order("AAPL", Side.BUY, quantity=10)

    execution = execute_order(broker, order, price=19.0)

    execution_model.calculate_fill_price.assert_called_once_with(19.0, Side.BUY)
    commission_model.calculate.assert_called_once_with(10, 20.0)
    assert portfolio.cash == 798.0
    portfolio.add_position.assert_called_once_with("AAPL", 10)
    portfolio.remove_position.assert_not_called()
    expected_trade = Trade(
        "AAPL",
        Side.BUY,
        quantity=10,
        fill_price=20.0,
        commission=2.0,
        timestamp=EXECUTION_TIMESTAMP,
    )
    assert execution.status is OrderExecutionStatus.SUCCESS
    assert execution.order == order
    assert execution.trade == expected_trade


@pytest.mark.parametrize(
    ("quantity", "commission"),
    [
        pytest.param(3, 0.0, id="notional-roundoff"),
        pytest.param(1, 0.2, id="commission-addition-roundoff"),
    ],
)
def test_buy_accepts_roundoff_and_clamps_remaining_cash_to_zero(
    quantity: int, commission: float,
) -> None:
    portfolio = make_portfolio_mock(cash=0.3)
    broker, _, _ = make_broker(portfolio, fill_price=0.1, commission=commission)
    order = make_order("AAPL", Side.BUY, quantity=quantity)
    assert quantity * 0.1 + commission > portfolio.cash

    execution = execute_order(broker, order, price=0.1)

    assert execution.status is OrderExecutionStatus.SUCCESS
    assert execution.trade is not None
    assert portfolio.cash == 0.0
    portfolio.add_position.assert_called_once_with("AAPL", quantity)
    portfolio.remove_position.assert_not_called()


def test_sell_accepts_commission_roundoff_and_clamps_remaining_cash_to_zero() -> None:
    portfolio = make_portfolio_mock(cash=0.0, owned_quantity=1)
    # Proceeds equal 0.3; the fee calculation rounds slightly above them.
    commission = 3 * 0.1
    broker, _, _ = make_broker(portfolio, fill_price=0.3, commission=commission)
    order = make_order("AAPL", Side.SELL, quantity=1)
    assert commission > portfolio.cash + 0.3

    execution = execute_order(broker, order, price=0.3)

    assert execution.status is OrderExecutionStatus.SUCCESS
    assert execution.trade is not None
    assert portfolio.cash == 0.0
    portfolio.remove_position.assert_called_once_with("AAPL", 1)
    portfolio.add_position.assert_not_called()


@pytest.mark.parametrize("side", [Side.BUY, Side.SELL])
def test_execution_rejects_shortfall_outside_tolerance_without_portfolio_updates(
    side: Side,
) -> None:
    portfolio = make_portfolio_mock(cash=0.3, owned_quantity=1)
    commission = 1e-8 if side is Side.BUY else 0.6 + 1e-8
    broker, _, _ = make_broker(portfolio, fill_price=0.3, commission=commission)
    order = make_order("AAPL", side, quantity=1)

    execution = execute_order(broker, order, price=0.3)

    assert execution.status is OrderExecutionStatus.INSUFFICIENT_FUNDS
    assert execution.trade is None
    assert portfolio.cash == 0.3
    portfolio.add_position.assert_not_called()
    portfolio.remove_position.assert_not_called()


@pytest.mark.parametrize("side", [Side.BUY, Side.SELL])
def test_execution_preserves_small_positive_cash_remainder(side: Side) -> None:
    portfolio = make_portfolio_mock(cash=0.3, owned_quantity=1)
    fill_price = 0.3 - 5e-10 if side is Side.BUY else 0.3
    commission = 0.0 if side is Side.BUY else 0.6 - 5e-10
    broker, _, _ = make_broker(portfolio, fill_price=fill_price, commission=commission)
    order = make_order("AAPL", side, quantity=1)

    execution = execute_order(broker, order, price=fill_price)

    assert execution.status is OrderExecutionStatus.SUCCESS
    assert 0.0 < portfolio.cash < 1e-9
    assert portfolio.cash == pytest.approx(5e-10, rel=1e-6, abs=0.0)


def test_buy_without_enough_cash_returns_rejection_without_updating_portfolio() -> None:
    portfolio = make_portfolio_mock(cash=100)
    broker, execution_model, commission_model = make_broker(
        portfolio,
        fill_price=20.0,
        commission=2.0,
    )
    order = make_order("AAPL", Side.BUY, quantity=6)

    execution = execute_order(broker, order, price=19.0)

    execution_model.calculate_fill_price.assert_called_once_with(19.0, Side.BUY)
    commission_model.calculate.assert_called_once_with(6, 20.0)
    assert portfolio.cash == 100
    portfolio.add_position.assert_not_called()
    portfolio.remove_position.assert_not_called()
    assert execution.status is OrderExecutionStatus.INSUFFICIENT_FUNDS
    assert execution.order == order
    assert execution.trade is None


def test_sell_order_uses_models_updates_portfolio_and_returns_trade() -> None:
    portfolio = make_portfolio_mock(cash=1_000, owned_quantity=10)
    broker, execution_model, commission_model = make_broker(
        portfolio,
        fill_price=25.0,
        commission=2.0,
    )
    order = make_order("AAPL", Side.SELL, quantity=4)

    execution = execute_order(broker, order, price=26.0)

    execution_model.calculate_fill_price.assert_called_once_with(26.0, Side.SELL)
    commission_model.calculate.assert_called_once_with(4, 25.0)
    portfolio.position_quantity.assert_called_once_with("AAPL")
    assert portfolio.cash == 1_098.0
    portfolio.remove_position.assert_called_once_with("AAPL", 4)
    portfolio.add_position.assert_not_called()
    expected_trade = Trade(
        "AAPL",
        Side.SELL,
        quantity=4,
        fill_price=25.0,
        commission=2.0,
        timestamp=EXECUTION_TIMESTAMP,
    )
    assert execution.status is OrderExecutionStatus.SUCCESS
    assert execution.order == order
    assert execution.trade == expected_trade


def test_sell_more_shares_than_owned_returns_rejection_without_updating_portfolio() -> None:
    portfolio = make_portfolio_mock(cash=1_000, owned_quantity=5)
    broker, execution_model, commission_model = make_broker(
        portfolio,
        fill_price=25.0,
        commission=2.0,
    )
    order = make_order("AAPL", Side.SELL, quantity=6)

    execution = execute_order(broker, order, price=26.0)

    execution_model.calculate_fill_price.assert_called_once_with(26.0, Side.SELL)
    commission_model.calculate.assert_called_once_with(6, 25.0)
    portfolio.position_quantity.assert_called_once_with("AAPL")
    assert portfolio.cash == 1_000
    portfolio.remove_position.assert_not_called()
    portfolio.add_position.assert_not_called()
    assert execution.status is OrderExecutionStatus.INSUFFICIENT_POSITION
    assert execution.order == order
    assert execution.trade is None


def test_sell_full_position_requests_position_removal() -> None:
    portfolio = make_portfolio_mock(cash=1_000, owned_quantity=5)
    broker, _, _ = make_broker(portfolio, fill_price=30.0, commission=2.0)

    execute_order(broker, make_order("AAPL", Side.SELL, quantity=5), price=31.0)

    assert portfolio.cash == 1_148.0
    portfolio.remove_position.assert_called_once_with("AAPL", 5)


def test_execute_rejects_missing_market_price_without_updating_portfolio() -> None:
    portfolio = make_portfolio_mock(cash=1_000)
    broker, execution_model, commission_model = make_broker(portfolio)
    order = make_order("AAPL", Side.BUY, quantity=1)

    with pytest.raises(PriceNotFoundError):
        broker.execute(
            order,
            prices={"MSFT": 20},
            timestamp=EXECUTION_TIMESTAMP,
        )

    execution_model.calculate_fill_price.assert_not_called()
    commission_model.calculate.assert_not_called()
    assert portfolio.cash == 1_000
    portfolio.add_position.assert_not_called()
    portfolio.remove_position.assert_not_called()


@pytest.mark.parametrize(
    ("side", "quantity"),
    [
        (Side.BUY, 0),
        (Side.SELL, -1),
    ],
)
def test_order_rejects_non_positive_quantity(side: Side, quantity: int) -> None:
    with pytest.raises(ValueError, match="Quantity must be positive"):
        make_order("AAPL", side, quantity=quantity)


def test_execute_rejects_non_positive_market_price_without_trade() -> None:
    portfolio = make_portfolio_mock(cash=1_000)
    broker, execution_model, commission_model = make_broker(portfolio)
    execution_model.calculate_fill_price.side_effect = ValueError(
        "reference_price must be positive"
    )
    order = make_order("AAPL", Side.BUY, quantity=1)

    with pytest.raises(ValueError, match="reference_price must be positive"):
        execute_order(broker, order, price=0)

    execution_model.calculate_fill_price.assert_called_once_with(0, Side.BUY)
    commission_model.calculate.assert_not_called()
    assert portfolio.cash == 1_000
    portfolio.add_position.assert_not_called()
    portfolio.remove_position.assert_not_called()


def test_order_rejects_empty_symbol() -> None:
    with pytest.raises(ValueError, match="Symbol must be a non-empty string"):
        make_order("", Side.BUY, quantity=1)


@pytest.mark.parametrize("side", [Side.BUY, Side.SELL])
def test_execute_rejects_fill_before_submission_without_side_effects(side: Side) -> None:
    portfolio = make_portfolio_mock(cash=1_000, owned_quantity=1)
    broker, execution_model, commission_model = make_broker(portfolio)
    order = make_order("AAPL", side, quantity=1)

    with pytest.raises(ValueError, match="Execution timestamp cannot precede order submission"):
        execute_order(broker, order, price=20, timestamp=SIGNAL_TIMESTAMP)

    execution_model.calculate_fill_price.assert_not_called()
    commission_model.calculate.assert_not_called()
    assert portfolio.cash == 1_000
    assert portfolio.mock_calls == []


def test_execute_accepts_fill_at_submission_timestamp() -> None:
    portfolio = make_portfolio_mock(cash=1_000)
    broker, _, _ = make_broker(portfolio)
    order = make_order("AAPL", Side.BUY, quantity=1)

    execution = execute_order(broker, order, price=20, timestamp=ORDER_TIMESTAMP)

    assert execution.status is OrderExecutionStatus.SUCCESS
    assert execution.trade.timestamp == ORDER_TIMESTAMP
    assert portfolio.cash == 978
    portfolio.add_position.assert_called_once_with("AAPL", 1)


def test_trade_rejects_non_positive_price() -> None:
    with pytest.raises(ValueError, match="Price must be positive"):
        Trade(
            "AAPL",
            Side.BUY,
            quantity=1,
            fill_price=0,
            commission=2.0,
            timestamp=EXECUTION_TIMESTAMP,
        )
