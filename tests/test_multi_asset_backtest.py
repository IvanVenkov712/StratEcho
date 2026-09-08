from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from backtester.domain.market import Candle, MarketFrame
from backtester.domain.trading import (
    MultiAssetSignal,
    OrderIntent,
    PortfolioSnapshot,
    Side,
    Signal,
    SizingInstruction,
    SizingMode,
)
from backtester.engine.backtest import BacktestEngine
from backtester.execution.broker import Broker
from backtester.resolving.resolver import OrderResolver
from backtester.sizing.asset_allocation import AssetAllocation
from backtester.sizing.policy import MultiAssetSizingPlan, SizingPlan
from backtester.strategies.multi_asset.base import MultiAssetStrategy


SYMBOLS = ("AAPL", "MSFT")
ALL_IN = SizingInstruction(mode=SizingMode.ALL_IN, value=None)
PLAN = SizingPlan(buy=ALL_IN, sell=ALL_IN)


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
        BacktestEngine(**engine_args)

    engine_args["strategy"].on_frame.assert_not_called()
    engine_args["resolver"].resolve.assert_not_called()
    engine_args["broker"].execute.assert_not_called()


def test_frame_error_identifies_timestamp_and_missing_and_unsupported_symbols(
    engine_args: dict,
) -> None:
    engine_args["data"] = [make_frame(("AAPL", "GOOG"))]

    with pytest.raises(ValueError) as error:
        BacktestEngine(**engine_args)

    assert "Frame at 2026-01-01" in str(error.value)
    assert "unsupported=['GOOG']" in str(error.value)
    assert "missing=['MSFT']" in str(error.value)


@pytest.mark.parametrize("signal", list(Signal))
def test_rejects_unsupported_signals_even_on_the_final_frame(
    engine_args: dict, signal: Signal,
) -> None:
    engine_args["strategy"].on_frame.return_value = MultiAssetSignal({"GOOG": signal})
    engine = BacktestEngine(**engine_args)

    with pytest.raises(ValueError, match="Strategy signal.*unsupported=.*GOOG"):
        engine.run()

    engine_args["resolver"].resolve.assert_not_called()
    engine_args["broker"].execute.assert_not_called()
    engine_args["broker"].portfolio.snapshot.assert_not_called()


@pytest.mark.parametrize("signals", [{}, {"MSFT": Signal.HOLD}, {"AAPL": Signal.BUY}])
def test_accepts_partial_signals(engine_args: dict, signals: dict[str, Signal]) -> None:
    engine_args["strategy"].on_frame.return_value = MultiAssetSignal(signals)

    result = BacktestEngine(**engine_args).run()

    assert result.records[0].generated_signal == MultiAssetSignal(signals)
    assert result.order_executions == []


def test_empty_data_still_validates_sizing(engine_args: dict) -> None:
    engine_args["data"] = []
    engine_args["sizing"] = MultiAssetSizingPlan({"AAPL": PLAN})

    with pytest.raises(ValueError, match="Sizing plan.*missing=.*MSFT"):
        BacktestEngine(**engine_args)


def test_zero_weight_symbol_is_still_supported(engine_args: dict) -> None:
    engine_args["allocation"] = AssetAllocation({"AAPL": 1.0, "MSFT": 0.0})
    engine_args["strategy"].on_frame.return_value = MultiAssetSignal({"MSFT": Signal.SELL})

    result = BacktestEngine(**engine_args).run()

    assert result.records[0].generated_signal.signals == {"MSFT": Signal.SELL}


def test_valid_empty_data_does_not_call_strategy(engine_args: dict) -> None:
    engine_args["data"] = []

    result = BacktestEngine(**engine_args).run()

    assert result.records == []
    engine_args["strategy"].on_frame.assert_not_called()


def test_supported_signal_reaches_resolver_at_next_frame_open(engine_args: dict) -> None:
    first, second = make_frame(), make_frame(day=1)
    engine_args["data"] = [first, second]
    engine_args["strategy"].on_frame.side_effect = [
        MultiAssetSignal({"MSFT": Signal.BUY}), MultiAssetSignal({}),
    ]

    BacktestEngine(**engine_args).run()

    engine_args["resolver"].resolve.assert_called_once()
    arguments = engine_args["resolver"].resolve.call_args.kwargs
    assert arguments["intent"] == OrderIntent("MSFT", Side.BUY, first.timestamp, ALL_IN)
    assert arguments["context"].timestamp == second.timestamp
    assert arguments["context"].reference_prices == second.open_prices()
