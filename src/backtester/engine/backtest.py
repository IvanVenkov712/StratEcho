"""Chronological backtest orchestration with next-candle-open execution."""

from datetime import datetime
from typing import Sequence

from backtester.data.validation import validate_candles_chronological
from backtester.domain.market import Candle
from backtester.domain.trading import Signal, Order, OrderIntent, Side, OrderExecutionResult
from backtester.engine.backtest_result import BacktestResult, BacktestRecord
from backtester.execution.broker import Broker
from backtester.resolving.resolver import OrderResolver, ResolutionContext
from backtester.sizing.policy import SizingPlan
from backtester.strategies.base import SingleAssetStrategy


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
            strategy: SingleAssetStrategy,
            broker: Broker,
            plan: SizingPlan,
            resolver: OrderResolver,
            data: Sequence[Candle],
            symbol: str
    ):
        """Create a backtest engine for one strategy, broker, data set, and symbol.

        Args:
            strategy: Trading strategy that converts available candle history
                into a buy, sell, or hold signal.
            broker: Broker responsible for order execution and portfolio
                accounting.
            plan: Buy and sell sizing instructions attached to generated order
                intents.
            resolver: Component that converts pending intents into whole-share
                orders using execution costs and the next candle's opening
                portfolio snapshot.
            data: Chronologically ordered candles used by the simulation.
            symbol: Asset symbol traded by this engine.
        """

        validated_data = tuple(data)
        validate_candles_chronological(validated_data)

        self._results = None
        self._strategy: SingleAssetStrategy = strategy
        self._broker = broker
        self._plan = plan
        self._resolver = resolver
        self._data = validated_data
        self._symbol = symbol
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
        order_executions = []
        trades = []
        records = []
        order_intent = None

        for candle in self._data:
            if order_intent is not None:
                order = self._create_order(order_intent, candle)
                if order is not None:
                    execution_result = self._execute_pending_order(order, candle)
                    order_executions.append(execution_result)
                    if execution_result.trade is not None:
                        trades.append(execution_result.trade)

            signal = self._strategy.on_candle(candle)
            order_intent = self._create_order_intent(candle.timestamp, signal)
            records.append(self._create_record(candle, signal))

        return BacktestResult(
            symbol=self._symbol,
            initial_cash=self._initial_cash,
            records=records,
            trades=trades,
            order_executions=order_executions
        )

    def _execute_pending_order(self, order: Order, candle: Candle) -> OrderExecutionResult:
        """Execute a pending order at the current candle open.

        Returns the broker's OrderExecutionResult. Insufficient cash or
        position is captured in its status instead of stopping the backtest.
        """
        return self._broker.execute(
            order=order,
            prices={self._symbol: candle.open},
            timestamp=candle.timestamp
        )

    def _create_order(self, intent: OrderIntent, candle: Candle) -> Order | None:
        """Convert a buy or sell signal into an execution-time order.

        The quantity is calculated from the portfolio state immediately before
        execution and the current candle's open. The simulation uses that same
        opening reference price for execution. The order retains the intent's
        signal timestamp and uses the current candle as its submission
        timestamp.
        """
        return self._resolver.resolve(
            intent=intent,
            context=self._create_context(candle.timestamp, candle.open)
        )

    def _create_order_intent(self, timestamp: datetime, signal: Signal) -> OrderIntent | None:
        if signal == Signal.BUY or signal == Signal.SELL:
            side = side_from_signal(signal)

            return OrderIntent(
                symbol=self._symbol,
                timestamp=timestamp,
                side=side,
                sizing_instruction=self._plan.instruction_for(side)
            )

        elif signal != Signal.HOLD:
            raise ValueError("Not a valid signal")

        return None

    def _create_record(self, candle: Candle, signal: Signal) -> BacktestRecord:
        """Create a per-candle snapshot valued at the current close."""
        return BacktestRecord(
            candle=candle,
            generated_signal=signal,
            snapshot=self._broker.portfolio.snapshot(prices={self._symbol: candle.close})
        )

    def _create_context(self, timestamp: datetime, price: float) -> ResolutionContext:
        current_quantity = self._broker.portfolio.position_quantity(self._symbol)
        cash = self._broker.portfolio.cash

        return ResolutionContext(
            timestamp=timestamp,
            reference_price=price,
            cash=cash,
            current_quantity=current_quantity,
            portfolio_value=cash + current_quantity * price
        )


def side_from_signal(signal: Signal) -> Side:
    """Map a buy or sell signal to its corresponding order side."""
    if signal == Signal.BUY:
        return Side.BUY
    elif signal == Signal.SELL:
        return Side.SELL
    else:
        raise ValueError("Invalid signal")
