"""Structured records returned by the backtest engine."""

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from backtester.domain.market import Candle, MarketFrame
from backtester.domain.trading import Signal, Trade, OrderExecutionResult, PortfolioSnapshot, MultiAssetSignal, \
    PendingDecision
from backtester.sizing.asset_allocation import AssetAllocation


@dataclass(frozen=True)
class BacktestRecord:
    """Signal and end-of-period portfolio snapshot for one candle."""
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
    """Run metadata, chronological records, trades, and attempted orders."""
    initial_cash: float
    records: Sequence[BacktestRecord]
    trades: Sequence[Trade]
    order_executions: Sequence[OrderExecutionResult]
