"""Chronological backtest orchestration with next-candle-open execution."""

from typing import Sequence

from backtester.data.validation import validate_frames_chronological, validate_symbols
from backtester.domain.market import MarketFrame
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
    Every frame must contain the same symbols. The executor validates those
    symbols against its configuration and validates each generated decision,
    including the final decision that cannot be executed.
    """

    def __init__(
            self,
            strategy: PortfolioStrategy,
            decision_executor: DecisionExecutor,
            data: Sequence[MarketFrame],
    ):
        """Create a backtest engine for one strategy and a shared portfolio.

        Args:
            strategy: Strategy observing each frame and its closing portfolio
                snapshot to produce a decision.
            decision_executor: Validates decisions and executes them through
                its broker using the next frame's opening prices.
            data: Chronologically ordered market frames used by the simulation.
                Empty data produces an empty result without calling the strategy.
        """

        validated_data = tuple(data)
        validate_frames_chronological(validated_data)
        supported_symbols = tuple(validated_data[0].candles) if validated_data else ()
        if validated_data:
            decision_executor.validate_universe(
                supported_symbols, source=f"Frame at {validated_data[0].timestamp}"
            )
        for frame in validated_data:
            validate_symbols(
                frame.candles, supported_symbols, source=f"Frame at {frame.timestamp}"
            )

        self._data = validated_data
        self._results: BacktestResult | None = None
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

            snapshot = self._decision_executor.broker.portfolio.snapshot(prices=frame.close_prices())
            decision = self._strategy.on_frame(frame, snapshot)
            self._decision_executor.validate_decision(decision, self._supported_symbols)
            records.append(BacktestRecord(frame, decision, snapshot))

        return BacktestResult(
            symbols=self._supported_symbols,
            initial_cash=self._initial_cash,
            records=records,
            trades=trades_total,
            order_executions=order_executions_total
        )
