from datetime import datetime
from unittest.mock import Mock, call

import pytest

from backtester.domain.trading import (
    Order,
    OrderExecutionResult,
    OrderExecutionStatus,
    OrderIntent,
    PortfolioSnapshot,
    Side,
    SizingInstruction,
    SizingMode,
    Trade,
)
from backtester.execution.broker import Broker
from backtester.execution.decision_execution.intent_executor import IntentExecutor
from backtester.order_resolving.order_resolver import OrderResolutionContext, OrderResolver
from backtester.sizing.asset_allocation import AssetAllocation


SIGNAL_TIME = datetime(2026, 1, 1)
EXECUTION_TIME = datetime(2026, 1, 2)


def make_intent(symbol: str, side: Side = Side.BUY, quantity: int = 1) -> OrderIntent:
    return OrderIntent(symbol, side, SIGNAL_TIME, SizingInstruction(quantity, SizingMode.FIXED))


def make_order(intent: OrderIntent, quantity: int = 1) -> Order:
    return Order(intent.symbol, intent.side, quantity, intent.timestamp, EXECUTION_TIME)


def successful_execution(order: Order) -> OrderExecutionResult:
    trade = Trade(order.symbol, order.side, order.quantity, 20.0, 1.0, EXECUTION_TIME)
    return OrderExecutionResult(OrderExecutionStatus.SUCCESS, order, trade)


@pytest.fixture
def broker() -> Mock:
    broker = Mock(spec=Broker)
    broker.portfolio.snapshot.return_value = PortfolioSnapshot(1000.0, 1000.0, {})
    return broker


@pytest.fixture
def resolver() -> Mock:
    return Mock(spec=OrderResolver)


def test_execute_passes_context_and_resolved_order_to_dependencies(
    broker: Mock, resolver: Mock,
) -> None:
    intent = make_intent("A", quantity=10)
    order = make_order(intent, quantity=10)
    execution = successful_execution(order)
    resolver.resolve.return_value = order
    broker.execute.return_value = execution
    prices = {"A": 19.0}
    allocation = AssetAllocation({"A": 0.5})
    executor = IntentExecutor(resolver, broker, lambda symbol: 0)

    result = executor.execute([intent], EXECUTION_TIME, prices, allocation)

    broker.portfolio.snapshot.assert_called_once_with(prices)
    resolver.resolve.assert_called_once_with(
        intent=intent,
        context=OrderResolutionContext(
            EXECUTION_TIME, prices, broker.portfolio.snapshot.return_value, allocation,
        ),
    )
    broker.execute.assert_called_once_with(order=order, prices=prices, timestamp=EXECUTION_TIME)
    assert result.order_executions == [execution]
    assert result.trades == [execution.trade]


@pytest.mark.parametrize(
    ("intents", "priorities", "expected_indices"),
    [
        pytest.param(
            [make_intent("A"), make_intent("Z", Side.SELL)],
            {"A": -10, "Z": 10}, [1, 0], id="sells-before-higher-priority-buys",
        ),
        pytest.param(
            [make_intent("A"), make_intent("Z")],
            {"A": 10, "Z": -10}, [1, 0], id="buy-priority-before-symbol",
        ),
        pytest.param(
            [make_intent("A", Side.SELL), make_intent("Z", Side.SELL)],
            {"A": 10, "Z": -10}, [1, 0], id="sell-priority-before-symbol",
        ),
        pytest.param(
            [make_intent("Z"), make_intent("A"),
             make_intent("Z", Side.SELL), make_intent("A", Side.SELL)],
            {"A": 0, "Z": 0}, [3, 2, 1, 0], id="symbol-breaks-priority-ties",
        ),
        pytest.param(
            [make_intent("A", quantity=2), make_intent("A", quantity=1)],
            {"A": 0}, [0, 1], id="equal-keys-preserve-input-order-and-duplicates",
        ),
    ],
)
def test_execute_orders_intents_without_mutating_input(
    broker: Mock, resolver: Mock, intents: list[OrderIntent],
    priorities: dict[str, int], expected_indices: list[int],
) -> None:
    original_intents = list(intents)
    expected_intents = [intents[index] for index in expected_indices]
    orders = [make_order(intent) for intent in expected_intents]
    executions = [successful_execution(order) for order in orders]
    resolver.resolve.side_effect = orders
    broker.execute.side_effect = executions
    prices = {symbol: 20.0 for symbol in priorities}
    allocation = AssetAllocation({symbol: 0.0 for symbol in priorities})
    executor = IntentExecutor(resolver, broker, priorities.__getitem__)

    result = executor.execute(intents, EXECUTION_TIME, prices, allocation)

    assert [entry.kwargs["intent"] for entry in resolver.resolve.call_args_list] == expected_intents
    assert broker.execute.call_args_list == [
        call(order=order, prices=prices, timestamp=EXECUTION_TIME) for order in orders
    ]
    assert result.order_executions == executions
    assert result.trades == [execution.trade for execution in executions]
    assert intents == original_intents


def test_execute_refreshes_snapshot_after_each_fill_before_resolving_next_intent(
    broker: Mock, resolver: Mock,
) -> None:
    sell = make_intent("A", Side.SELL)
    buy = make_intent("B")
    sell_order, buy_order = make_order(sell), make_order(buy)
    # Selling one share at 20 with a commission of 1 leaves cash and equity of 19.
    before_sale = PortfolioSnapshot(0.0, 20.0, {"A": 1})
    after_sale = PortfolioSnapshot(19.0, 19.0, {})
    broker.portfolio.snapshot.side_effect = [before_sale, after_sale]
    resolver.resolve.side_effect = [sell_order, buy_order]
    buy_execution = OrderExecutionResult(
        OrderExecutionStatus.SUCCESS, buy_order,
        Trade("B", Side.BUY, 1, 10.0, 1.0, EXECUTION_TIME),
    )
    broker.execute.side_effect = [successful_execution(sell_order), buy_execution]
    calls = Mock()
    calls.attach_mock(broker.portfolio.snapshot, "snapshot")
    calls.attach_mock(resolver.resolve, "resolve")
    calls.attach_mock(broker.execute, "execute")
    prices = {"A": 20.0, "B": 10.0}
    allocation = AssetAllocation({"A": 0.0, "B": 1.0})
    executor = IntentExecutor(resolver, broker, lambda symbol: 0)

    executor.execute([buy, sell], EXECUTION_TIME, prices, allocation)

    assert calls.mock_calls == [
        call.snapshot(prices),
        call.resolve(intent=sell, context=OrderResolutionContext(
            EXECUTION_TIME, prices, before_sale, allocation,
        )),
        call.execute(order=sell_order, prices=prices, timestamp=EXECUTION_TIME),
        call.snapshot(prices),
        call.resolve(intent=buy, context=OrderResolutionContext(
            EXECUTION_TIME, prices, after_sale, allocation,
        )),
        call.execute(order=buy_order, prices=prices, timestamp=EXECUTION_TIME),
    ]


def test_execute_empty_intents_does_not_call_dependencies(broker: Mock, resolver: Mock) -> None:
    priority = Mock()
    executor = IntentExecutor(resolver, broker, priority)

    result = executor.execute([], EXECUTION_TIME, {}, AssetAllocation({}))

    assert result.order_executions == []
    assert result.trades == []
    priority.assert_not_called()
    broker.portfolio.snapshot.assert_not_called()
    resolver.resolve.assert_not_called()
    broker.execute.assert_not_called()


@pytest.mark.parametrize("skip_all", [False, True], ids=["skip-between-fills", "all-skipped"])
def test_execute_omits_skipped_intents_and_continues(
    broker: Mock, resolver: Mock, skip_all: bool,
) -> None:
    intents = [make_intent(symbol) for symbol in ("A", "B", "C")]
    orders = [make_order(intents[0]), make_order(intents[2])]
    executions = [successful_execution(order) for order in orders]
    resolver.resolve.side_effect = [None, None, None] if skip_all else [orders[0], None, orders[1]]
    broker.execute.side_effect = executions
    prices = {intent.symbol: 20.0 for intent in intents}
    allocation = AssetAllocation({intent.symbol: 0.0 for intent in intents})
    executor = IntentExecutor(resolver, broker, lambda symbol: 0)

    result = executor.execute(tuple(intents), EXECUTION_TIME, prices, allocation)

    assert [entry.kwargs["intent"] for entry in resolver.resolve.call_args_list] == intents
    assert broker.portfolio.snapshot.call_args_list == [call(prices)] * 3
    expected_orders = [] if skip_all else orders
    assert broker.execute.call_args_list == [
        call(order=order, prices=prices, timestamp=EXECUTION_TIME) for order in expected_orders
    ]
    assert result.order_executions == ([] if skip_all else executions)
    assert result.trades == ([] if skip_all else [execution.trade for execution in executions])


@pytest.mark.parametrize("status", [
    OrderExecutionStatus.INSUFFICIENT_FUNDS,
    OrderExecutionStatus.INSUFFICIENT_POSITION,
])
def test_execute_records_rejection_without_trade_and_continues(
    broker: Mock, resolver: Mock, status: OrderExecutionStatus,
) -> None:
    intents = [make_intent("A"), make_intent("B")]
    orders = [make_order(intent) for intent in intents]
    rejection = OrderExecutionResult(status, orders[0], None)
    success = successful_execution(orders[1])
    resolver.resolve.side_effect = orders
    broker.execute.side_effect = [rejection, success]
    prices = {"A": 20.0, "B": 20.0}
    executor = IntentExecutor(resolver, broker, lambda symbol: 0)

    result = executor.execute(intents, EXECUTION_TIME, prices, AssetAllocation({"A": 0.5, "B": 0.5}))

    assert result.order_executions == [rejection, success]
    assert result.trades == [success.trade]
    assert broker.execute.call_args_list == [
        call(order=order, prices=prices, timestamp=EXECUTION_TIME) for order in orders
    ]
    assert broker.portfolio.snapshot.call_args_list == [call(prices), call(prices)]


@pytest.mark.parametrize("failing_dependency", ["snapshot", "resolver", "broker"])
def test_execute_propagates_dependency_errors_and_stops_processing(
    broker: Mock, resolver: Mock, failing_dependency: str,
) -> None:
    intents = [make_intent("A"), make_intent("B")]
    resolver.resolve.return_value = make_order(intents[0])
    error = ValueError("Invalid execution input")
    dependency = {
        "snapshot": broker.portfolio.snapshot,
        "resolver": resolver.resolve,
        "broker": broker.execute,
    }[failing_dependency]
    dependency.side_effect = error
    executor = IntentExecutor(resolver, broker, lambda symbol: 0)

    with pytest.raises(ValueError) as caught:
        executor.execute(intents, EXECUTION_TIME, {}, AssetAllocation({}))

    assert caught.value is error
    broker.portfolio.snapshot.assert_called_once_with({})
    assert resolver.resolve.call_count == (0 if failing_dependency == "snapshot" else 1)
    assert broker.execute.call_count == (1 if failing_dependency == "broker" else 0)


def test_execute_does_not_reuse_results_between_calls(broker: Mock, resolver: Mock) -> None:
    intent = make_intent("A")
    order = make_order(intent)
    execution = successful_execution(order)
    resolver.resolve.return_value = order
    broker.execute.return_value = execution
    executor = IntentExecutor(resolver, broker, lambda symbol: 0)
    allocation = AssetAllocation({"A": 1.0})

    first = executor.execute([intent], EXECUTION_TIME, {"A": 20.0}, allocation)
    second = executor.execute([], EXECUTION_TIME, {"A": 20.0}, allocation)

    assert first.order_executions == [execution]
    assert first.trades == [execution.trade]
    assert second.order_executions == []
    assert second.trades == []
