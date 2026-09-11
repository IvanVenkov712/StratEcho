from datetime import datetime
from typing import Callable, Sequence

from backtester.data.validation import validate_symbols
from backtester.domain.trading import PendingDecision, SignalDecision, OrderIntent, Side, Order, MultiAssetSignal, \
    Signal, OrderExecutionResult
from backtester.execution.broker import Broker
from backtester.execution.decision_execution.decision_executor import DecisionExecutionResult, DecisionExecutor
from backtester.order_resolving.order_resolver import OrderResolver, OrderResolutionContext
from backtester.sizing.asset_allocation import AssetAllocation
from backtester.sizing.policy import MultiAssetSizingPlan


class SignalDecisionExecutor(DecisionExecutor):
    def __init__(
            self,
            broker: Broker,
            resolver: OrderResolver,
            sizing: MultiAssetSizingPlan,
            allocation: AssetAllocation,
            priority: Callable[[str], int],
    ):
        supported_symbols = frozenset(allocation.allocations)
        validate_symbols(sizing.plans, supported_symbols, source="Sizing plan")
        self._resolver = resolver
        self._priority = priority
        self._broker = broker
        self._allocation = allocation
        self._sizing = sizing
        self._supported_symbols = supported_symbols

    def execute(
            self,
            pending_decision: PendingDecision,
            timestamp: datetime,
            prices: dict[str, float]
    ) -> DecisionExecutionResult:
        if not isinstance(pending_decision, SignalDecision):
            raise ValueError("SignalDecision is expected")

        signal_decision: SignalDecision = pending_decision
        intents = self._create_order_intents(timestamp, signal_decision.signal)
        return self._order_execution_results(intents, timestamp, prices)

    def _order_execution_results(
            self,
            intents: Sequence[OrderIntent],
            timestamp: datetime,
            prices: dict[str, float]
    ) -> DecisionExecutionResult:
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
            order = self._create_order(intent, timestamp, prices)
            if order is not None:
                exec_result = self._execute_pending_order(order, timestamp, prices)
                exec_results.append(exec_result)
                if exec_result.trade is not None:
                    trades.append(exec_result.trade)

        return DecisionExecutionResult(exec_results, trades)

    def _create_order(self, intent: OrderIntent, timestamp: datetime, prices: dict[str, float]) -> Order | None:
        context = self._create_order_resolution_context(timestamp, prices)

        return self._resolver.resolve(
            intent=intent,
            context=context
        )

    def _create_order_intents(
            self, timestamp: datetime,
            multi_asset_signal: MultiAssetSignal
    ) -> Sequence[OrderIntent]:

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

    def _create_order_resolution_context(
            self,
            timestamp: datetime,
            prices: dict[str, float]
    ) -> OrderResolutionContext:
        """Value the current portfolio at frame opens after any earlier fills."""

        return OrderResolutionContext(
            timestamp=timestamp,
            reference_prices=prices,
            snapshot=self._broker.portfolio.snapshot(prices),
            allocation=self._allocation
        )

    def _execute_pending_order(
            self,
            order: Order,
            timestamp: datetime,
            prices: dict[str, float]
    ) -> OrderExecutionResult:

        return self._broker.execute(
            order=order,
            prices=prices,
            timestamp=timestamp
        )


def side_from_signal(signal: Signal) -> Side:
    """Map a buy or sell signal to its corresponding order side."""
    if signal == Signal.BUY:
        return Side.BUY
    elif signal == Signal.SELL:
        return Side.SELL
    else:
        raise ValueError("Invalid signal")