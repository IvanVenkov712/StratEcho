from datetime import datetime, timedelta
from unittest.mock import Mock, call

import pytest

from backtester.domain.market import Candle, MarketFrame
from backtester.domain.trading import (
    MultiAssetSignal,
    Order,
    OrderExecutionResult,
    OrderExecutionStatus,
    OrderIntent,
    PortfolioSnapshot,
    Side,
    Signal,
    SizingInstruction,
    SizingMode,
    Trade,
)
from backtester.engine.backtest import BacktestEngine
from backtester.execution.broker import Broker
from backtester.execution.decision_execution.intent_executor import IntentExecutor
from backtester.execution.decision_execution.signal_decision_executor import SignalDecisionExecutor
from backtester.domain.trading import SignalDecision
from backtester.order_resolving.order_resolver import OrderResolver, OrderResolutionContext
from backtester.sizing.asset_allocation import AssetAllocation
from backtester.sizing.policy import MultiAssetSizingPlan, SizingPlan
from backtester.strategies.multi_asset.base import MultiAssetStrategy
from backtester.strategies.portfolio_strategies.portfolio_strategy import MultiAssetPortfolioStrategy


SYMBOLS = ("AAPL", "MSFT")
ALL_IN = SizingInstruction(mode=SizingMode.ALL_IN, value=None)
PLAN = SizingPlan(buy=ALL_IN, sell=ALL_IN)


def make_engine(*, strategy, broker, allocation, sizing, resolver, priority, data) -> BacktestEngine:
    """Wire the signal pipeline with mocked strategy, broker, and resolver."""
    return BacktestEngine(
        strategy=MultiAssetPortfolioStrategy(strategy),
        decision_executor=SignalDecisionExecutor(
            IntentExecutor(resolver, broker, priority), sizing, allocation,
        ),
        data=data,
    )


def make_frame(symbols: tuple[str, ...] = SYMBOLS, day: int = 0) -> MarketFrame:
    timestamp = datetime(2026, 1, 1) + timedelta(days=day)
    candle = Candle(timestamp, open=100, high=100, low=100, close=100, volume=10)
    return MarketFrame(timestamp, {symbol: candle for symbol in symbols})


@pytest.fixture
def engine_args() -> dict:
    strategy = Mock(spec=MultiAssetStrategy)
    strategy.on_frame.return_value = MultiAssetSignal({})
    broker = Mock(spec=Broker)
    broker.portfolio = Mock(cash=1_000)
    broker.portfolio.snapshot.return_value = PortfolioSnapshot(1_000, 1_000, {})
    resolver = Mock(spec=OrderResolver)
    resolver.resolve.return_value = None
    return {
        "strategy": strategy,
        "broker": broker,
        "allocation": AssetAllocation({symbol: 0.5 for symbol in SYMBOLS}),
        "sizing": MultiAssetSizingPlan({symbol: PLAN for symbol in SYMBOLS}),
        "resolver": resolver,
        "priority": Mock(return_value=0),
        "data": [make_frame()],
    }


@pytest.mark.parametrize("component", ["allocation", "sizing", "frame"])
@pytest.mark.parametrize(
    "symbols",
    [("AAPL",), ("AAPL", "MSFT", "GOOG"), ("AAPL", "GOOG"), ()],
    ids=["missing", "extra", "replacement", "empty"],
)
def test_rejects_mismatched_configuration_before_processing(
    engine_args: dict, component: str, symbols: tuple[str, ...],
) -> None:
    if component == "allocation":
        engine_args["allocation"] = AssetAllocation({symbol: 0.25 for symbol in symbols})
    elif component == "sizing":
        engine_args["sizing"] = MultiAssetSizingPlan({symbol: PLAN for symbol in symbols})
    else:
        # Check every frame, including later frames with a changed universe.
        engine_args["data"].append(make_frame(symbols, day=1))

    with pytest.raises(ValueError, match="symbols do not match supported symbols"):
        make_engine(**engine_args)

    engine_args["strategy"].on_frame.assert_not_called()
    engine_args["resolver"].resolve.assert_not_called()
    engine_args["broker"].execute.assert_not_called()


def test_frame_error_identifies_timestamp_and_missing_and_unsupported_symbols(
    engine_args: dict,
) -> None:
    engine_args["data"] = [make_frame(("AAPL", "GOOG"))]

    with pytest.raises(ValueError) as error:
        make_engine(**engine_args)

    assert "Frame at 2026-01-01" in str(error.value)
    assert "unsupported=['GOOG']" in str(error.value)
    assert "missing=['MSFT']" in str(error.value)


@pytest.mark.parametrize("symbols", [("GOOG",), ("AAPL",), ("AAPL", "MSFT", "GOOG"), ()])
def test_matching_allocation_and_sizing_must_also_match_market_data(
    engine_args: dict, symbols: tuple[str, ...],
) -> None:
    engine_args["allocation"] = AssetAllocation({symbol: 0.25 for symbol in symbols})
    engine_args["sizing"] = MultiAssetSizingPlan({symbol: PLAN for symbol in symbols})

    with pytest.raises(ValueError, match="Frame at.*symbols do not match"):
        make_engine(**engine_args)

    engine_args["strategy"].on_frame.assert_not_called()
    engine_args["resolver"].resolve.assert_not_called()
    engine_args["broker"].execute.assert_not_called()


@pytest.mark.parametrize("invalid_signal", [None, "buy", 1])
def test_final_frame_invalid_signal_value_is_rejected(engine_args: dict, invalid_signal: object) -> None:
    engine_args["strategy"].on_frame.return_value = MultiAssetSignal({"AAPL": invalid_signal})

    with pytest.raises(ValueError, match="Not a valid signal"):
        make_engine(**engine_args).run()

    engine_args["resolver"].resolve.assert_not_called()
    engine_args["broker"].execute.assert_not_called()


@pytest.mark.parametrize("signal", list(Signal))
def test_rejects_unsupported_signals_even_on_the_final_frame(
    engine_args: dict, signal: Signal,
) -> None:
    engine_args["strategy"].on_frame.return_value = MultiAssetSignal({"GOOG": signal})
    engine = make_engine(**engine_args)

    with pytest.raises(ValueError, match="Strategy signal.*unsupported=.*GOOG"):
        engine.run()

    engine_args["resolver"].resolve.assert_not_called()
    engine_args["broker"].execute.assert_not_called()
    engine_args["broker"].portfolio.snapshot.assert_called_once_with(prices=engine_args["data"][0].close_prices())


@pytest.mark.parametrize("signals", [{}, {"MSFT": Signal.HOLD}, {"AAPL": Signal.BUY}])
def test_accepts_partial_signals(engine_args: dict, signals: dict[str, Signal]) -> None:
    engine_args["strategy"].on_frame.return_value = MultiAssetSignal(signals)

    result = make_engine(**engine_args).run()

    assert result.records[0].generated_decision == SignalDecision(engine_args["data"][0].timestamp, MultiAssetSignal(signals))
    assert result.order_executions == []


def test_empty_data_still_validates_sizing(engine_args: dict) -> None:
    engine_args["data"] = []
    engine_args["sizing"] = MultiAssetSizingPlan({"AAPL": PLAN})

    with pytest.raises(ValueError, match="Sizing plan.*missing=.*MSFT"):
        make_engine(**engine_args)


def test_zero_weight_symbol_is_still_supported(engine_args: dict) -> None:
    engine_args["allocation"] = AssetAllocation({"AAPL": 1.0, "MSFT": 0.0})
    engine_args["strategy"].on_frame.return_value = MultiAssetSignal({"MSFT": Signal.SELL})

    result = make_engine(**engine_args).run()

    assert result.records[0].generated_decision.signal.signals == {"MSFT": Signal.SELL}


def test_valid_empty_data_does_not_call_strategy(engine_args: dict) -> None:
    engine_args["data"] = []

    result = make_engine(**engine_args).run()

    assert result.records == []
    engine_args["strategy"].on_frame.assert_not_called()


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_partial_signal_only_resolves_present_symbol_at_next_frame_open(
    engine_args: dict, symbol: str,
) -> None:
    first, second = make_frame(), make_frame(day=1)
    engine_args["data"] = [first, second]
    engine_args["strategy"].on_frame.side_effect = [
        MultiAssetSignal({symbol: Signal.BUY}), MultiAssetSignal({}),
    ]

    make_engine(**engine_args).run()

    engine_args["resolver"].resolve.assert_called_once()
    arguments = engine_args["resolver"].resolve.call_args.kwargs
    assert arguments["intent"] == OrderIntent(symbol, Side.BUY, first.timestamp, ALL_IN)
    assert arguments["context"].timestamp == second.timestamp
    assert arguments["context"].reference_prices == second.open_prices()


def make_execution(order: Order, *, commission: float = 0) -> OrderExecutionResult:
    """Represent a scripted fill at 100 with no slippage."""
    return OrderExecutionResult(
        status=OrderExecutionStatus.SUCCESS,
        order=order,
        trade=Trade(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            fill_price=100,
            commission=commission,
            timestamp=order.submitted_timestamp,
        ),
    )


@pytest.mark.parametrize(
    ("priorities", "expected_symbols"),
    [
        pytest.param({"AAPL": 1, "MSFT": 0}, ("MSFT", "AAPL"), id="msft-first"),
        pytest.param({"AAPL": 0, "MSFT": 1}, ("AAPL", "MSFT"), id="aapl-first"),
        pytest.param({"AAPL": 0, "MSFT": 0}, ("AAPL", "MSFT"), id="symbol-tie-break"),
    ],
)
@pytest.mark.parametrize("commission", [0, 10], ids=["no-fees", "flat-fee"])
def test_simultaneous_buys_share_refreshed_cash_and_equity_in_priority_order(
    engine_args: dict, priorities: dict[str, int], expected_symbols: tuple[str, str],
    commission: float,
) -> None:
    first, second = make_frame(), make_frame(day=1)
    earlier, later = expected_symbols
    engine_args["data"] = [first, second]
    engine_args["priority"] = Mock(side_effect=priorities.__getitem__)
    # Deliberately oppose alphabetical order in the strategy's signal mapping.
    engine_args["strategy"].on_frame.side_effect = [
        MultiAssetSignal({"MSFT": Signal.BUY, "AAPL": Signal.BUY}),
        MultiAssetSignal({}),
    ]
    portfolio = engine_args["broker"].portfolio
    portfolio.cash = 1_020
    before = PortfolioSnapshot(1_020, 1_020, {})
    # Half of 1,020 is 510: five shares cost 500 plus the optional fee.
    after_first = PortfolioSnapshot(520 - commission, 1_020 - commission, {earlier: 5})
    # With a 10 fee, the second target is 505; five shares plus 10 no longer fit.
    later_quantity = 5 if commission == 0 else 4
    final = (
        PortfolioSnapshot(20, 1_020, {earlier: 5, later: 5})
        if commission == 0
        else PortfolioSnapshot(100, 1_000, {earlier: 5, later: 4})
    )
    portfolio.snapshot.side_effect = [before, before, after_first, final]
    orders = [
        Order(earlier, Side.BUY, 5, first.timestamp, second.timestamp),
        Order(later, Side.BUY, later_quantity, first.timestamp, second.timestamp),
    ]
    engine_args["resolver"].resolve.side_effect = orders
    executions = [make_execution(order, commission=commission) for order in orders]
    engine_args["broker"].execute.side_effect = executions

    result = make_engine(**engine_args).run()

    assert engine_args["resolver"].resolve.call_args_list == [
        call(
            intent=OrderIntent(symbol, Side.BUY, first.timestamp, ALL_IN),
            context=OrderResolutionContext(
                second.timestamp, second.open_prices(), snapshot, engine_args["allocation"],
            ),
        )
        for symbol, snapshot in [(earlier, before), (later, after_first)]
    ]
    assert engine_args["broker"].execute.call_args_list == [
        call(order=order, prices=second.open_prices(), timestamp=second.timestamp)
        for order in orders
    ]
    assert result.order_executions == executions
    assert result.trades == [execution.trade for execution in executions]
    assert result.records[-1].snapshot == final


def test_sell_funds_another_assets_buy_at_the_same_open(engine_args: dict) -> None:
    first, second = make_frame(), make_frame(day=1)
    engine_args["data"] = [first, second]
    engine_args["strategy"].on_frame.side_effect = [
        MultiAssetSignal({"AAPL": Signal.BUY, "MSFT": Signal.SELL}),
        MultiAssetSignal({}),
    ]
    # Side ordering wins even when the buy has higher priority.
    engine_args["priority"] = Mock(side_effect={"AAPL": 0, "MSFT": 1}.__getitem__)
    portfolio = engine_args["broker"].portfolio
    portfolio.cash = 0
    before = PortfolioSnapshot(0, 1_000, {"MSFT": 10})
    after_sale = PortfolioSnapshot(1_000, 1_000, {})
    final = PortfolioSnapshot(500, 1_000, {"AAPL": 5})
    portfolio.snapshot.side_effect = [before, before, after_sale, final]
    orders = [
        Order("MSFT", Side.SELL, 10, first.timestamp, second.timestamp),
        Order("AAPL", Side.BUY, 5, first.timestamp, second.timestamp),
    ]
    engine_args["resolver"].resolve.side_effect = orders
    executions = [make_execution(order) for order in orders]
    engine_args["broker"].execute.side_effect = executions
    events = Mock()
    events.attach_mock(engine_args["resolver"].resolve, "resolve")
    events.attach_mock(engine_args["broker"].execute, "execute")
    events.attach_mock(engine_args["strategy"].on_frame, "on_frame")

    result = make_engine(**engine_args).run()

    assert events.mock_calls == [
        call.on_frame(first),
        call.resolve(
            intent=OrderIntent("MSFT", Side.SELL, first.timestamp, ALL_IN),
            context=OrderResolutionContext(
                second.timestamp, second.open_prices(), before, engine_args["allocation"],
            ),
        ),
        call.execute(order=orders[0], prices=second.open_prices(), timestamp=second.timestamp),
        call.resolve(
            intent=OrderIntent("AAPL", Side.BUY, first.timestamp, ALL_IN),
            context=OrderResolutionContext(
                second.timestamp, second.open_prices(), after_sale, engine_args["allocation"],
            ),
        ),
        call.execute(order=orders[1], prices=second.open_prices(), timestamp=second.timestamp),
        call.on_frame(second),
    ]
    assert result.order_executions == executions
    assert result.trades == [execution.trade for execution in executions]
    assert result.records[-1].snapshot == final


def test_final_frame_multi_asset_signals_are_recorded_without_execution(engine_args: dict) -> None:
    first, final = make_frame(), make_frame(day=1)
    signal = MultiAssetSignal({"AAPL": Signal.BUY, "MSFT": Signal.SELL})
    engine_args["data"] = [first, final]
    engine_args["strategy"].on_frame.side_effect = [MultiAssetSignal({}), signal]

    engine = make_engine(**engine_args)
    result = engine.run()

    assert engine.run() is result
    assert result.records[-1].frame is final
    assert result.records[-1].generated_decision == SignalDecision(final.timestamp, signal)
    assert result.order_executions == []
    assert result.trades == []
    engine_args["resolver"].resolve.assert_not_called()
    engine_args["broker"].execute.assert_not_called()
    assert engine_args["strategy"].on_frame.call_args_list == [call(first), call(final)]
