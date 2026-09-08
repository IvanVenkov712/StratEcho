"""Chronological backtest orchestration with next-candle-open execution."""

from datetime import datetime
from typing import Sequence

from backtester.data.validation import validate_frames_chronological
from backtester.domain.market import MarketFrame
from backtester.domain.trading import Signal, Order, OrderIntent, Side, OrderExecutionResult, MultiAssetSignal
from backtester.engine.backtest_result import BacktestResult, BacktestRecord
from backtester.execution.broker import Broker
from backtester.resolving.resolver import OrderResolver, OrderResolutionContext
from backtester.sizing.asset_allocation import AssetAllocation
from backtester.sizing.policy import MultiAssetSizingPlan
from backtester.strategies.multi_asset.base import MultiAssetStrategy


class BacktestEngine:
    """Run a single-symbol backtest with explicit next-candle execution.

    The engine feeds the strategy only the candles available up to the current
    point in time. A signal generated from candle T creates an order intent.
    At candle T+1 open, the position sizer uses the current portfolio and opening
    price to determine the order quantity immediately before execution. This
    keeps signal generation separate from execution and avoids look-ahead bias.
    """

    def __init__(
            self,
            strategy: MultiAssetStrategy,
            broker: Broker,
            allocation: AssetAllocation,
            sizing: MultiAssetSizingPlan,
            resolver: OrderResolver,
            data: Sequence[MarketFrame],
    ):
        """Create a backtest engine for one strategy, broker, data set, and symbol.

        Args:
            strategy: Trading strategy that converts available candle history
                into a buy, sell, or hold signal.
            broker: Broker responsible for order execution and portfolio
                accounting.
            allocation: Buy and sell sizing instructions attached to generated order
                intents.
            resolver: Component that converts pending intents into whole-share
                orders using execution costs and the next candle's opening
                portfolio snapshot.
            data: Chronologically ordered candles used by the simulation.
            symbol: Asset symbol traded by this engine.
        """

        validated_data = tuple(data)
        validate_frames_chronological(validated_data)

        self._results = None
        self._strategy: MultiAssetStrategy = strategy
        self._broker = broker
        self._allocation = allocation
        self._sizing = sizing
        self._resolver = resolver
        self._data = validated_data
        self._initial_cash = broker.portfolio.cash

    def run(self) -> BacktestResult:
        """Run the backtest once and return the cached result on later calls."""
        if self._results is None:
            self._results = self._calculate_results()

        return self._results

    def _calculate_results(self) -> BacktestResult:
        """Iterate through candles, execute pending orders, and record results.

        For each candle, an intent created by the previous candle's signal is
        sized from the current portfolio and executed first at the current open.
        The current candle is then added to the strategy's available history, a
        new signal is generated, and the portfolio is valued at the current
        close.
        """
        order_executions_total = []
        trades = []
        records = []
        order_intents = []

        for frame in self._data:
            orders = self._create_orders(order_intents, frame)
            execution_results = self._execute_pending_orders(orders, frame)
            order_executions_total.extend(execution_results)
            trades.extend([
                    res.trade
                    for res in execution_results
                    if res.trade is not None
                ]
            )

            signal = self._strategy.on_frame(frame)
            order_intents = self._create_order_intents(frame.timestamp, signal)
            records.append(self._create_record(frame, signal))

        return BacktestResult(
            allocation=self._allocation,
            initial_cash=self._initial_cash,
            records=records,
            trades=trades,
            order_executions=order_executions_total
        )

    def _execute_pending_orders(self, orders: Sequence[Order], frame: MarketFrame) -> Sequence[OrderExecutionResult]:
        """Execute a pending order at the current candle open.

        Returns the broker's OrderExecutionResult. Insufficient cash or
        position is captured in its status instead of stopping the backtest.
        """
        prices = frame.open_prices()
        return [
            self._broker.execute(
                order=order,
                prices=prices,
                timestamp=frame.timestamp
            )
            for order in orders
        ]

    def _create_orders(self, intents: Sequence[OrderIntent], frame: MarketFrame) -> Sequence[Order]:
        """Convert a buy or sell signal into an execution-time order.

        The quantity is calculated from the portfolio state immediately before
        execution and the current candle's open. The simulation uses that same
        opening reference price for execution. The order retains the intent's
        signal timestamp and uses the current candle as its submission
        timestamp.
        """
        context = self._create_order_resolution_context(frame)

        return [
            order for intent in intents
            if (
                order := self._resolver.resolve(
                    intent=intent,
                    context=context
                )
            ) is not None
        ]


    def _create_order_intents(self, timestamp: datetime, multi_asset_signal: MultiAssetSignal) -> Sequence[OrderIntent]:
        intents = []

        for symbol, signal in multi_asset_signal.signals.items():

            if signal == Signal.BUY or signal == Signal.SELL:

                side = side_from_signal(signal)
                plan = self._sizing.plans[symbol]

                intents.append(OrderIntent(
                    symbol=symbol,
                    timestamp=timestamp,
                    side=side,
                    sizing_instruction=plan.instruction_for(side)
                ))

            elif signal != Signal.HOLD:
                raise ValueError("Not a valid signal")

        return intents

    def _create_record(self, frame: MarketFrame, signal: MultiAssetSignal) -> BacktestRecord:
        """Create a per-candle snapshot valued at the current close."""
        return BacktestRecord(
            frame=frame,
            generated_signal=signal,
            snapshot=self._broker.portfolio.snapshot(prices=frame.close_prices())
        )

    def _create_order_resolution_context(self, frame: MarketFrame) -> OrderResolutionContext:
        reference_prices = frame.open_prices()

        return OrderResolutionContext(
            timestamp=frame.timestamp,
            reference_prices=reference_prices,
            snapshot=self._broker.portfolio.snapshot(reference_prices),
            allocation=self._allocation
        )

def side_from_signal(signal: Signal) -> Side:
    """Map a buy or sell signal to its corresponding order side."""
    if signal == Signal.BUY:
        return Side.BUY
    elif signal == Signal.SELL:
        return Side.SELL
    else:
        raise ValueError("Invalid signal")
