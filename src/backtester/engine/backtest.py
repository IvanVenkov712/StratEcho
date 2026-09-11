"""Chronological backtest orchestration with next-candle-open execution."""

from typing import Sequence

from backtester.data.validation import validate_frames_chronological, validate_symbols
from backtester.domain.market import MarketFrame
from backtester.domain.trading import PendingDecision
from backtester.engine.backtest_result import BacktestResult, BacktestRecord
from backtester.execution.decision_execution.decision_executor import DecisionExecutor
from backtester.strategies.portfolio_strategies.portfolio_strategy import PortfolioStrategy


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
            strategy: PortfolioStrategy,
            decision_executor: DecisionExecutor,
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
        supported_symbols = frozenset(data[0].candles)
        for frame in validated_data:
            validate_symbols(
                frame.candles, supported_symbols, source=f"Frame at {frame.timestamp}"
            )

        self._data = validated_data
        self._results = None
        self._supported_symbols = supported_symbols
        self._strategy = strategy
        self._decision_executor = decision_executor
        self._initial_cash = decision_executor.broker.portfolio.cash

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
        decision = None

        for frame in self._data:

            if decision is not None:
                exec_result = self._decision_executor.execute(
                    decision, frame.timestamp, frame.open_prices()
                )
                order_executions_total.extend(exec_result.order_executions)
                trades_total.extend(exec_result.trades)

            decision = self._strategy.on_frame(
                frame,
                self._decision_executor.broker.portfolio.snapshot(frame.close_prices())
            )
            records.append(self._create_record(frame, decision))

        return BacktestResult(
            initial_cash=self._initial_cash,
            records=records,
            trades=trades_total,
            order_executions=order_executions_total
        )



    def _create_record(self, frame: MarketFrame, decision: PendingDecision) -> BacktestRecord:
        """Create a per-candle snapshot valued at the current close."""
        return BacktestRecord(
            frame=frame,
            generated_decision=decision,
            snapshot=self._decision_executor.broker.portfolio.snapshot(prices=frame.close_prices())
        )
