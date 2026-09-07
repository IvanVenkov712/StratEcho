from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from unittest.mock import Mock, call

import pytest

from backtester.domain.market import Candle
from backtester.engine.backtest import BacktestEngine
from backtester.resolving.resolver import OrderResolver, ResolutionContext
from backtester.sizing.policy import SizingPlan
from backtester.domain.trading import (
    Order,
    OrderIntent,
    Side,
    Signal,
    SizingInstruction,
    SizingMode,
    PortfolioSnapshot,
    Trade,
    OrderExecutionResult,
    OrderExecutionStatus,
)
from backtester.strategies.base import SingleAssetStrategy


ALL_IN_INSTRUCTION = SizingInstruction(mode=SizingMode.ALL_IN, value=None)
DEFAULT_SIZING_PLAN = SizingPlan(
    buy=ALL_IN_INSTRUCTION,
    sell=ALL_IN_INSTRUCTION,
)


def make_portfolio_mock(
    cash: float = 1_000,
    *,
    position_quantity: int = 0,
    value_at_close: float | None = None,
) -> Mock:
    portfolio = Mock()
    portfolio.cash = cash
    portfolio.position_quantity.return_value = position_quantity
    portfolio.value.return_value = cash if value_at_close is None else value_at_close

    def snapshot(prices: Mapping[str, float]) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            cash=portfolio.cash,
            value=portfolio.value(prices),
            positions={},
        )

    portfolio.snapshot.side_effect = snapshot
    return portfolio


def make_broker_mock(
    portfolio: Mock | None = None,
    *,
    rejection_statuses: Sequence[OrderExecutionStatus] = (),
    on_execute: Callable[[Order, Mapping[str, float], datetime], None] | None = None,
) -> Mock:
    broker = Mock()
    broker.portfolio = portfolio or make_portfolio_mock()
    pending_rejections = list(rejection_statuses)

    def execute(
        order: Order,
        prices: Mapping[str, float],
        timestamp: datetime,
    ) -> OrderExecutionResult:
        if pending_rejections:
            return OrderExecutionResult(
                status=pending_rejections.pop(0),
                order=order,
                trade=None,
            )

        if on_execute is not None:
            on_execute(order, prices, timestamp)

        trade = Trade(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            fill_price=prices[order.symbol],
            commission=1.0,
            timestamp=timestamp,
        )
        return OrderExecutionResult(
            status=OrderExecutionStatus.SUCCESS,
            order=order,
            trade=trade,
        )

    broker.execute.side_effect = execute
    return broker


def make_resolver_mock(*quantities: int) -> Mock:
    resolver = Mock(spec=OrderResolver)
    configured_quantities = quantities or (10,)

    if len(configured_quantities) == 1:
        pending_quantities = None
    else:
        pending_quantities = iter(configured_quantities)

    def resolve(intent: OrderIntent, context: ResolutionContext) -> Order | None:
        quantity = (
            configured_quantities[0]
            if pending_quantities is None
            else next(pending_quantities)
        )
        if quantity <= 0:
            return None

        return Order(
            symbol=intent.symbol,
            side=intent.side,
            quantity=quantity,
            signal_timestamp=intent.timestamp,
            submitted_timestamp=context.timestamp,
        )

    resolver.resolve.side_effect = resolve
    return resolver


def make_candles(prices: Sequence[tuple[float, float]]) -> list[Candle]:
    start = datetime(2026, 1, 1)
    candles = []

    for index, (open_price, close_price) in enumerate(prices):
        candles.append(
            Candle(
                timestamp=start + timedelta(days=index),
                open=open_price,
                high=max(open_price, close_price),
                low=min(open_price, close_price),
                close=close_price,
                volume=1_000,
            )
        )

    return candles


def make_engine(
    signals: Sequence[Signal],
    candles: Sequence[Candle],
    broker: Mock | None = None,
    resolver: Mock | None = None,
    plan: SizingPlan = DEFAULT_SIZING_PLAN,
) -> tuple[BacktestEngine, Mock, Mock]:
    strategy = Mock(spec=SingleAssetStrategy)
    strategy.on_candle.side_effect = list(signals)
    broker = broker or make_broker_mock()
    resolver = resolver or make_resolver_mock()
    engine = BacktestEngine(
        strategy=strategy,
        broker=broker,
        allocation=plan,
        resolver=resolver,
        data=candles,
        symbol="AAPL",
    )

    return engine, strategy, broker


def test_empty_data_produces_empty_result_without_calling_strategy() -> None:
    engine, strategy, broker = make_engine([Signal.BUY], candles=[])

    result = engine.run()

    assert result.records == []
    assert result.order_executions == []
    assert result.trades == []
    assert result.symbol == "AAPL"
    assert result.initial_cash == 1_000
    strategy.on_candle.assert_not_called()
    broker.execute.assert_not_called()


def test_engine_rejects_candles_that_are_not_chronological() -> None:
    candles = make_candles([(10, 10), (11, 11)])
    candles.reverse()

    with pytest.raises(ValueError, match="strictly increasing"):
        make_engine([Signal.HOLD, Signal.HOLD], candles)


def test_hold_strategy_creates_records_without_orders_or_trades() -> None:
    candles = make_candles([(10, 10), (11, 11), (12, 12)])
    engine, _, broker = make_engine([Signal.HOLD, Signal.HOLD, Signal.HOLD], candles)

    result = engine.run()

    assert len(result.records) == 3
    assert [record.generated_signal for record in result.records] == [
        Signal.HOLD,
        Signal.HOLD,
        Signal.HOLD,
    ]
    assert result.order_executions == []
    assert result.trades == []
    broker.execute.assert_not_called()


def test_buy_signal_creates_no_order_when_resolver_returns_none() -> None:
    candles = make_candles([(100, 100), (90, 90)])
    broker = make_broker_mock(make_portfolio_mock(cash=99))
    resolver = make_resolver_mock(0)
    engine, _, broker = make_engine(
        [Signal.BUY, Signal.HOLD], candles, broker, resolver
    )

    result = engine.run()

    assert result.order_executions == []
    assert result.trades == []
    broker.execute.assert_not_called()


def test_buy_signal_is_executed_on_next_candle_open() -> None:
    candles = make_candles([(100, 100), (90, 95)])
    engine, _, broker = make_engine([Signal.BUY, Signal.HOLD], candles)

    result = engine.run()

    assert len(result.order_executions) == 1
    assert result.order_executions[0].status is OrderExecutionStatus.SUCCESS
    assert result.order_executions[0].order == Order(
        symbol="AAPL",
        side=Side.BUY,
        quantity=10,
        signal_timestamp=candles[0].timestamp,
        submitted_timestamp=candles[1].timestamp,
    )
    broker.execute.assert_called_once_with(
        order=result.order_executions[0].order,
        prices={"AAPL": 90},
        timestamp=candles[1].timestamp,
    )
    assert result.trades == [result.order_executions[0].trade]


def test_pending_intent_sizes_order_from_portfolio_and_next_open() -> None:
    candles = make_candles([(50, 60), (70, 75)])
    broker = make_broker_mock(
        make_portfolio_mock(cash=1_000, position_quantity=4)
    )
    resolver = make_resolver_mock(3)
    engine, _, _ = make_engine(
        [Signal.BUY, Signal.HOLD], candles, broker, resolver
    )

    engine.run()

    resolver.resolve.assert_called_once_with(
        intent=OrderIntent(
            symbol="AAPL",
            side=Side.BUY,
            timestamp=candles[0].timestamp,
            sizing_instruction=ALL_IN_INSTRUCTION,
        ),
        context=ResolutionContext(
            timestamp=candles[1].timestamp,
            usable_cash=1_000,
            current_quantity=4,
            portfolio_value=1_280,
            reference_price=70,
        ),
    )


def test_buy_signal_on_last_candle_is_not_executed() -> None:
    candles = make_candles([(100, 100)])
    engine, _, broker = make_engine([Signal.BUY], candles)

    result = engine.run()

    assert result.order_executions == []
    assert result.trades == []
    broker.execute.assert_not_called()


def test_sell_signal_creates_no_order_when_resolver_returns_none() -> None:
    candles = make_candles([(20, 20), (25, 25)])
    resolver = make_resolver_mock(0)
    engine, _, broker = make_engine(
        [Signal.SELL, Signal.HOLD], candles, resolver=resolver
    )

    result = engine.run()

    assert result.order_executions == []
    assert result.trades == []
    broker.execute.assert_not_called()


def test_sell_signal_is_executed_on_next_candle_open() -> None:
    candles = make_candles([(20, 20), (25, 30)])
    broker = make_broker_mock(make_portfolio_mock(cash=100, position_quantity=5))
    resolver = make_resolver_mock(5)
    engine, _, broker = make_engine(
        [Signal.SELL, Signal.HOLD], candles, broker, resolver
    )

    result = engine.run()

    assert len(result.order_executions) == 1
    assert result.order_executions[0].status is OrderExecutionStatus.SUCCESS
    assert result.order_executions[0].order == Order(
        symbol="AAPL",
        side=Side.SELL,
        quantity=5,
        signal_timestamp=candles[0].timestamp,
        submitted_timestamp=candles[1].timestamp,
    )
    broker.execute.assert_called_once_with(
        order=result.order_executions[0].order,
        prices={"AAPL": 25},
        timestamp=candles[1].timestamp,
    )


def test_failed_pending_order_is_recorded_without_trade() -> None:
    candles = make_candles([(10, 10), (20, 20)])
    broker = make_broker_mock(
        make_portfolio_mock(cash=100),
        rejection_statuses=[OrderExecutionStatus.INSUFFICIENT_FUNDS],
    )
    engine, _, broker = make_engine([Signal.BUY, Signal.HOLD], candles, broker)

    result = engine.run()

    assert len(result.order_executions) == 1
    assert result.order_executions[0].status is OrderExecutionStatus.INSUFFICIENT_FUNDS
    assert result.order_executions[0].trade is None
    assert result.trades == []
    assert broker.execute.call_count == 1


def test_failed_pending_order_does_not_stop_current_candle_signal() -> None:
    candles = make_candles([(10, 10), (20, 50), (10, 10)])
    broker = make_broker_mock(
        make_portfolio_mock(cash=100),
        rejection_statuses=[OrderExecutionStatus.INSUFFICIENT_FUNDS],
    )
    engine, _, broker = make_engine(
        [Signal.BUY, Signal.BUY, Signal.HOLD],
        candles,
        broker,
        make_resolver_mock(10, 2),
    )

    result = engine.run()

    assert [order.status for order in result.order_executions] == [
        OrderExecutionStatus.INSUFFICIENT_FUNDS,
        OrderExecutionStatus.SUCCESS
    ]
    submitted_orders = [
        call_args.kwargs["order"] for call_args in broker.execute.call_args_list
    ]
    assert submitted_orders == [
        Order(
            "AAPL",
            Side.BUY,
            quantity=10,
            signal_timestamp=candles[0].timestamp,
            submitted_timestamp=candles[1].timestamp,
        ),
        Order(
            "AAPL",
            Side.BUY,
            quantity=2,
            signal_timestamp=candles[1].timestamp,
            submitted_timestamp=candles[2].timestamp,
        ),
    ]
    assert result.trades == [
        Trade(
            "AAPL",
            Side.BUY,
            quantity=2,
            fill_price=10,
            commission=1.0,
            timestamp=candles[2].timestamp,
        )
    ]


def test_run_is_idempotent_and_does_not_execute_trades_twice() -> None:
    candles = make_candles([(100, 100), (90, 95)])
    engine, _, broker = make_engine([Signal.BUY, Signal.HOLD], candles)

    first_result = engine.run()
    second_result = engine.run()

    assert second_result is first_result
    assert len(second_result.trades) == 1
    assert broker.execute.call_count == 1


def test_record_after_pending_order_uses_current_portfolio_snapshot_at_close() -> None:
    candles = make_candles([(100, 100), (80, 120)])
    portfolio = make_portfolio_mock(cash=1_000, value_at_close=1_000)

    def mark_execution_visible_in_next_record(
        _order: Order,
        _prices: Mapping[str, float],
        _timestamp: datetime,
    ) -> None:
        portfolio.cash = 200
        portfolio.value.return_value = 1_400

    broker = make_broker_mock(
        portfolio,
        on_execute=mark_execution_visible_in_next_record,
    )
    engine, _, _ = make_engine([Signal.BUY, Signal.HOLD], candles, broker)

    result = engine.run()

    assert result.records[0].frame is candles[0]
    assert result.records[0].snapshot.value == 1_000
    assert result.records[0].snapshot.cash == 1_000
    assert result.records[1].frame is candles[1]
    assert result.records[1].snapshot.value == 1_400
    assert result.records[1].snapshot.cash == 200
    portfolio.snapshot.assert_has_calls(
        [call(prices={"AAPL": 100}), call(prices={"AAPL": 120})]
    )


def test_pending_order_executes_before_current_candle_signal_is_generated() -> None:
    candles = make_candles([(100, 100), (90, 95), (110, 110)])
    portfolio = make_portfolio_mock(cash=1_000, position_quantity=0)

    def expose_position_after_buy(
        order: Order,
        _prices: Mapping[str, float],
        _timestamp: datetime,
    ) -> None:
        if order.side == Side.BUY:
            portfolio.position_quantity.return_value = order.quantity

    broker = make_broker_mock(portfolio, on_execute=expose_position_after_buy)
    engine, _, broker = make_engine(
        [Signal.BUY, Signal.SELL, Signal.HOLD],
        candles,
        broker,
    )

    result = engine.run()

    submitted_orders = [
        call_args.kwargs["order"] for call_args in broker.execute.call_args_list
    ]
    assert submitted_orders == [
        Order(
            "AAPL",
            Side.BUY,
            quantity=10,
            signal_timestamp=candles[0].timestamp,
            submitted_timestamp=candles[1].timestamp,
        ),
        Order(
            "AAPL",
            Side.SELL,
            quantity=10,
            signal_timestamp=candles[1].timestamp,
            submitted_timestamp=candles[2].timestamp,
        ),
    ]
    assert result.order_executions[1].status is OrderExecutionStatus.SUCCESS


def test_strategy_receives_each_candle_in_chronological_order() -> None:
    candles = make_candles([(10, 10), (11, 11), (12, 12)])
    engine, strategy, _ = make_engine(
        [Signal.HOLD, Signal.HOLD, Signal.HOLD],
        candles,
    )

    engine.run()

    assert strategy.on_candle.call_args_list == [call(candle) for candle in candles]


def test_buy_hold_sell_sequence_emits_expected_pending_orders() -> None:
    candles = make_candles([(100, 100), (90, 100), (110, 110), (130, 130)])
    portfolio = make_portfolio_mock(cash=1_000, position_quantity=0)

    def expose_position_after_buy(
        order: Order,
        _prices: Mapping[str, float],
        _timestamp: datetime,
    ) -> None:
        if order.side == Side.BUY:
            portfolio.position_quantity.return_value = order.quantity

    broker = make_broker_mock(portfolio, on_execute=expose_position_after_buy)
    engine, _, broker = make_engine(
        [Signal.BUY, Signal.HOLD, Signal.SELL, Signal.HOLD],
        candles,
        broker,
    )

    result = engine.run()

    submitted_orders = [
        call_args.kwargs["order"] for call_args in broker.execute.call_args_list
    ]
    assert submitted_orders == [
        Order(
            "AAPL",
            Side.BUY,
            quantity=10,
            signal_timestamp=candles[0].timestamp,
            submitted_timestamp=candles[1].timestamp,
        ),
        Order(
            "AAPL",
            Side.SELL,
            quantity=10,
            signal_timestamp=candles[2].timestamp,
            submitted_timestamp=candles[3].timestamp,
        ),
    ]
    submitted_prices = [
        call_args.kwargs["prices"] for call_args in broker.execute.call_args_list
    ]
    assert submitted_prices == [
        {"AAPL": 90},
        {"AAPL": 130},
    ]
    assert [order.status for order in result.order_executions] == [
        OrderExecutionStatus.SUCCESS, OrderExecutionStatus.SUCCESS
    ]
