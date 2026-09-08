from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from backtester.domain.market import Candle, MarketFrame
from backtester.domain.trading import MultiAssetSignal, Signal
from backtester.strategies.base import SingleAssetStrategy
from backtester.strategies.multi_asset.simple_multi_asset import (
    SameForAll,
    SimpleMultiAssetStrategy,
)


def make_frame(day: int = 0) -> MarketFrame:
    timestamp = datetime(2026, 1, 1) + timedelta(days=day)
    return MarketFrame(timestamp, {
        "AAPL": Candle(timestamp, 100, 100, 100, 100, 10),
        "MSFT": Candle(timestamp, 200, 200, 200, 200, 20),
    })


def test_rejects_one_strategy_instance_assigned_to_multiple_symbols() -> None:
    shared = Mock(spec=SingleAssetStrategy)

    with pytest.raises(ValueError, match="AAPL.*MSFT.*share a strategy instance"):
        SimpleMultiAssetStrategy({"AAPL": shared, "MSFT": shared})


def test_rejects_supplier_returning_a_shared_instance() -> None:
    supplier = Mock(return_value=Mock(spec=SingleAssetStrategy))

    with pytest.raises(ValueError, match="each symbol must have its own strategy instance"):
        SameForAll({"AAPL", "MSFT"}, supplier)

    assert supplier.call_count == 2


def test_each_symbol_has_independent_signal_history_and_is_reset() -> None:
    first = Mock(spec=SingleAssetStrategy)
    second = Mock(spec=SingleAssetStrategy)
    first.on_candle.side_effect = [Signal.BUY, Signal.HOLD]
    second.on_candle.side_effect = [Signal.BUY, Signal.HOLD]
    supplier = Mock(side_effect=[first, second])
    strategy = SameForAll({"AAPL", "MSFT"}, supplier)
    frames = [make_frame(), make_frame(day=1)]

    assert strategy.on_frame(frames[0]) == MultiAssetSignal({
        "AAPL": Signal.BUY, "MSFT": Signal.BUY,
    })
    assert strategy.on_frame(frames[1]) == MultiAssetSignal({
        "AAPL": Signal.HOLD, "MSFT": Signal.HOLD,
    })
    assert supplier.call_count == 2
    observed_prices = set()
    for child in (first, second):
        observed = [args.args[0] for args in child.on_candle.call_args_list]
        assert [candle.timestamp for candle in observed] == [frame.timestamp for frame in frames]
        assert observed[0].close == observed[1].close
        observed_prices.add(observed[0].close)
    assert observed_prices == {100, 200}

    strategy.reset()

    first.reset.assert_called_once_with()
    second.reset.assert_called_once_with()


def test_copies_strategy_mapping_to_preserve_instance_ownership() -> None:
    aapl = Mock(spec=SingleAssetStrategy)
    msft = Mock(spec=SingleAssetStrategy)
    strategies = {"AAPL": aapl, "MSFT": msft}
    strategy = SimpleMultiAssetStrategy(strategies)
    strategies["MSFT"] = aapl
    frame = make_frame()

    strategy.on_frame(frame)

    aapl.on_candle.assert_called_once_with(frame.candles["AAPL"])
    msft.on_candle.assert_called_once_with(frame.candles["MSFT"])


def test_checks_all_required_candles_before_advancing_any_strategy() -> None:
    aapl = Mock(spec=SingleAssetStrategy)
    msft = Mock(spec=SingleAssetStrategy)
    strategy = SimpleMultiAssetStrategy({"AAPL": aapl, "MSFT": msft})
    frame = make_frame()
    incomplete = MarketFrame(frame.timestamp, {"AAPL": frame.candles["AAPL"]})

    with pytest.raises(ValueError, match="Strategy input.*MSFT"):
        strategy.on_frame(incomplete)

    aapl.on_candle.assert_not_called()
    msft.on_candle.assert_not_called()


def test_can_generate_signals_for_a_subset_of_the_frame() -> None:
    child = Mock(spec=SingleAssetStrategy)
    child.on_candle.return_value = Signal.BUY
    strategy = SimpleMultiAssetStrategy({"AAPL": child})

    assert strategy.on_frame(make_frame()) == MultiAssetSignal({"AAPL": Signal.BUY})
