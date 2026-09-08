"""Chronological backtest orchestration with next-candle-open execution."""

from datetime import datetime
from typing import Sequence, Callable

from backtester.data.validation import validate_frames_chronological, validate_symbols
from backtester.domain.market import MarketFrame
from backtester.domain.trading import Signal, Order, OrderIntent, Side, OrderExecutionResult, MultiAssetSignal, Trade
from backtester.engine.backtest_result import BacktestResult, BacktestRecord
from backtester.execution.broker import Broker
from backtester.resolving.resolver import OrderResolver, OrderResolutionContext
from backtester.sizing.asset_allocation import AssetAllocation
from backtester.sizing.policy import MultiAssetSizingPlan
from backtester.strategies.multi_asset.base import MultiAssetStrategy


class BacktestEngine:
    """Run a multi-asset backtest with next-frame-open execution.

    Signals generated from frame T create intents for frame T+1 open. Pending
    sells precede buys; within each side, lower priority values execute first,
    with symbol order breaking ties. Each intent is sized from a fresh opening
    portfolio snapshot, including the effects of earlier fills in that frame.

    The strategy receives the current frame only after pending execution.
    Allocation weights constrain buy sizing without generating rebalance orders.
    Allocation keys define the supported symbols. Every frame and the sizing
    plan must contain exactly those symbols; signals may contain a subset.
    """

    def __init__(
            self,
            strategy: MultiAssetStrategy,
            broker: Broker,
            allocation: AssetAllocation,
            sizing: MultiAssetSizingPlan,
            resolver: OrderResolver,
            priority: Callable[[str], int],
            data: Sequence[MarketFrame],
    ):
        """Create a backtest engine for one strategy and a shared portfolio.

        Args:
            strategy: Trading strategy that processes chronological market
                frames and produces per-symbol buy, sell, or hold signals.
            broker: Broker responsible for order execution and portfolio
                accounting.
            allocation: Per-symbol fractions of total equity used as buy-sizing
                targets, without automatic rebalancing or cash reservation.
            sizing: Per-symbol buy and sell instructions attached to intents.
            resolver: Component that converts pending intents into whole-share
                orders using execution costs and the next frame's opening
                portfolio snapshot.
            priority: Symbol ranking within each order side; lower values execute
                first, with lexicographic symbol order breaking ties.
            data: Chronologically ordered market frames used by the simulation.
        """

        validated_data = tuple(data)
        validate_frames_chronological(validated_data)
        supported_symbols = frozenset(allocation.allocations)
        validate_symbols(sizing.plans, supported_symbols, source="Sizing plan")
        for frame in validated_data:
            validate_symbols(
                frame.candles, supported_symbols, source=f"Frame at {frame.timestamp}"
            )

        self._results = None
        self._supported_symbols = supported_symbols
        self._strategy: MultiAssetStrategy = strategy
        self._broker = broker
        self._allocation = allocation
        self._sizing = sizing
        self._resolver = resolver
        self._priority = priority
        self._data = validated_data
        self._initial_cash = broker.portfolio.cash

    def run(self) -> BacktestResult:
        """Run the backtest once and return the cached result on later calls."""
        if self._results is None:
            self._results = self._calculate_results()

        return self._results

    def _calculate_results(self) -> BacktestResult:
        """Execute pending intents at each frame's open, then generate signals.

        After execution, the strategy observes the current frame and the
        portfolio is recorded at closing prices. Signals from the final frame
        remain unexecuted because there is no following execution frame.
        """
        order_executions_total = []
        trades_total = []
        records = []
        order_intents = []

        for frame in self._data:

            exec_results, trades = self._order_execution_results(
                order_intents, frame
            )
            order_executions_total.extend(exec_results)
            trades_total.extend(trades)

            signal = self._strategy.on_frame(frame)
            order_intents = self._create_order_intents(frame.timestamp, signal)
            records.append(self._create_record(frame, signal))

        return BacktestResult(
            allocation=self._allocation,
            initial_cash=self._initial_cash,
            records=records,
            trades=trades_total,
            order_executions=order_executions_total
        )

    def _execute_pending_order(self, order: Order, frame: MarketFrame) -> OrderExecutionResult:
        prices = frame.open_prices()
        return self._broker.execute(
            order=order,
            prices=prices,
            timestamp=frame.timestamp
        )

    def _order_execution_results(
        self,
        intents: Sequence[OrderIntent],
        frame: MarketFrame
    ) -> tuple[Sequence[OrderExecutionResult], Sequence[Trade]]:
        """Resolve and execute intents sequentially at this frame's open.

        Sort by sells before buys, ascending priority, then symbol. Refresh the
        opening snapshot before every resolution: sale proceeds can fund later
        buys, and earlier fills change cash, holdings, and equity after costs.
        Consequently, later allocation budgets can depend on execution order.

        Only orders submitted to the broker produce execution results. Intents
        skipped by the resolver, including unaffordable fixed buys, are omitted.
        """

        def intent_key(intent: OrderIntent) -> tuple[int, int, str]:
            first = 0 if intent.side == Side.SELL else 1
            second = self._priority(intent.symbol)
            return first, second, intent.symbol

        sorted_intents = sorted(
            intents,
            key=intent_key
        )

        trades = []
        exec_results = []

        for intent in sorted_intents:
            order = self._create_order(intent, frame)
            if order is not None:
                exec_result = self._execute_pending_order(order, frame)
                exec_results.append(exec_result)
                if exec_result.trade is not None:
                    trades.append(exec_result.trade)

        return exec_results, trades

    def _create_order(self, intent: OrderIntent, frame: MarketFrame) -> Order | None:
        context = self._create_order_resolution_context(frame)

        return self._resolver.resolve(
            intent=intent,
            context=context
        )


    def _create_order_intents(self, timestamp: datetime, multi_asset_signal: MultiAssetSignal) -> Sequence[OrderIntent]:
        validate_symbols(
            multi_asset_signal.signals,
            self._supported_symbols,
            source=f"Strategy signal at {timestamp}",
            require_all=False,
        )
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
        """Value the current portfolio at frame opens after any earlier fills."""
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
