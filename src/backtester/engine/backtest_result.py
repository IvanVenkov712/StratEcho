"""Structured records returned by the backtest engine."""

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from backtester.domain.market import MarketFrame
from backtester.domain.trading import Trade, OrderExecutionResult, PortfolioSnapshot, PendingDecision


@dataclass(frozen=True)
class BacktestRecord:
    """Decision and end-of-period portfolio snapshot for one market frame."""
    frame: MarketFrame
    generated_decision: PendingDecision
    snapshot: PortfolioSnapshot

    @property
    def timestamp(self) -> datetime:
        return self.frame.timestamp

    @property
    def market_value(self) -> float:
        return self.snapshot.value - self.snapshot.cash

@dataclass(frozen=True)
class BacktestResult:
    """Observed symbols, chronological records, trades, and attempted orders.

    Symbols follow the first frame's order, independently of allocation weights.
    An empty run has no observed symbols.
    """
    symbols: tuple[str, ...]
    initial_cash: float
    records: Sequence[BacktestRecord]
    trades: Sequence[Trade]
    order_executions: Sequence[OrderExecutionResult]
