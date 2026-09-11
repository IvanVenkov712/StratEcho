from datetime import datetime
from collections.abc import Collection
from typing import Sequence, cast

from backtester.data.validation import validate_symbols
from backtester.domain.trading import PendingDecision, SignalDecision, OrderIntent, Side, MultiAssetSignal, \
    Signal
from backtester.execution.decision_execution.decision_executor import DecisionExecutionResult, DecisionExecutor
from backtester.execution.decision_execution.intent_executor import IntentExecutor
from backtester.sizing.asset_allocation import AssetAllocation
from backtester.sizing.policy import MultiAssetSizingPlan


class SignalDecisionExecutor(DecisionExecutor):
    def __init__(
            self,
            intent_executor: IntentExecutor,
            sizing: MultiAssetSizingPlan,
            allocation: AssetAllocation,
    ):
        super().__init__(intent_executor.broker)
        supported_symbols = frozenset(allocation.allocations)
        validate_symbols(sizing.plans, supported_symbols, source="Sizing plan")
        self._intent_executor = intent_executor
        self._allocation = allocation
        self._sizing = sizing
        self._supported_symbols = supported_symbols

    def validate_universe(self, symbols: Collection[str], *, source: str = "Market data") -> None:
        """Require prices for exactly the configured allocation symbols."""
        validate_symbols(symbols, self._supported_symbols, source=source)

    def validate_decision(self, decision: PendingDecision, symbols: Collection[str]) -> None:
        """Validate signal type, universe, and values before any order is created."""
        if not isinstance(decision, SignalDecision):
            raise ValueError("SignalDecision is expected")
        self.validate_universe(symbols)
        validate_symbols(
            decision.signal.signals,
            self._supported_symbols,
            source=f"Strategy signal at {decision.timestamp}",
            require_all=False,
        )
        if any(not isinstance(signal, Signal) for signal in decision.signal.signals.values()):
            raise ValueError("Not a valid signal")

    def execute(
            self,
            pending_decision: PendingDecision,
            timestamp: datetime,
            prices: dict[str, float]
    ) -> DecisionExecutionResult:
        self.validate_decision(pending_decision, prices.keys())

        signal_decision = cast(SignalDecision, pending_decision)
        intents = self._create_order_intents(signal_decision.timestamp, signal_decision.signal)
        return self._intent_executor.execute(intents, timestamp, prices, self._allocation)

    def _create_order_intents(
            self, timestamp: datetime,
            multi_asset_signal: MultiAssetSignal
    ) -> Sequence[OrderIntent]:

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

def side_from_signal(signal: Signal) -> Side:
    """Map a buy or sell signal to its corresponding order side."""
    if signal == Signal.BUY:
        return Side.BUY
    elif signal == Signal.SELL:
        return Side.SELL
    else:
        raise ValueError("Invalid signal")
