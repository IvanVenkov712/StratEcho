"""Run the local MSFT sample backtest used by the graphics demo."""

from pathlib import Path

from backtester.data.frames import market_frames_from_candles
from backtester.data.loader import CSVDataSource, candles_from_dataframe
from backtester.domain.trading import SizingInstruction, SizingMode
from backtester.engine.backtest import BacktestEngine
from backtester.engine.backtest_result import BacktestResult
from backtester.execution.broker import Broker
from backtester.execution.costs import (
    ExecutionModel,
    ProportionalCommissionModel,
    ExecutionCostCalculator,
)
from backtester.portfolio.portfolio import Portfolio
from backtester.resolving.resolver import OrderResolver, QuantityResolver, BuyQuantityCapper
from backtester.sizing.asset_allocation import AssetAllocation
from backtester.sizing.policy import MultiAssetSizingPlan, SizingPlan
from backtester.strategies.multi_asset.simple_multi_asset import SimpleMultiAssetStrategy
from backtester.strategies.rsi_strategies import WilderRSIStrategy


def load_results() -> BacktestResult:
    """Load repository CSV data and run RSI with next-candle-open fills.

    Start with 10,000 cash and allocate up to 100% to MSFT in whole shares;
    sell signals liquidate the position. Slippage and proportional commission
    each use a rate of 0.00001 (0.001%) per trade.
    """
    source = CSVDataSource(Path(__file__).resolve().parents[3] / "data" / "MSFT.csv")
    data = source.load("MSFT", "2021-01-01", "2026-01-01")
    if data is None or data.empty:
        raise ValueError("No MSFT sample data available for 2021-01-01 to 2026-01-01.")
    candles = candles_from_dataframe(data)
    frames = market_frames_from_candles({"MSFT": candles})

    exec_model = ExecutionModel(0.00001)
    comm_model = ProportionalCommissionModel(0.00001)
    cost_calculator = ExecutionCostCalculator(exec_model, comm_model)
    broker = Broker(
        execution_model=exec_model,
        commission_model=comm_model,
        portfolio=Portfolio(10_000)
    )
    resolver = OrderResolver(QuantityResolver(BuyQuantityCapper(cost_calculator)))
    plan = SizingPlan(
        SizingInstruction(None, SizingMode.ALL_IN),
        SizingInstruction(None, SizingMode.ALL_IN)
    )

    engine = BacktestEngine(
        strategy=SimpleMultiAssetStrategy({"MSFT": WilderRSIStrategy(30, 70)}),
        broker=broker,
        allocation=AssetAllocation({"MSFT": 1.0}),
        sizing=MultiAssetSizingPlan({"MSFT": plan}),
        resolver=resolver,
        priority=lambda symbol: 0,
        data=frames,
    )
    return engine.run()
