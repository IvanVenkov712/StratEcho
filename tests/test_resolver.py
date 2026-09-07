from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from backtester.execution.costs import CommissionModel, ExecutionModel, ExecutionCostCalculator
from backtester.resolving.resolver import (
    BufferQuantityResolver,
    BuyQuantityCapper,
    OrderResolver,
    QuantityResolver,
    ResolutionContext,
)
from backtester.domain.trading import Side, SizingMode, SizingInstruction, Order, OrderIntent

TIMESTAMP = datetime(2024, 1, 2, 9, 30)


def make_context(
    *,
    reference_price: float = 100.0,
    cash: float = 1_000.0,
    current_quantity: int = 10,
    portfolio_value: float = 2_000.0,
) -> ResolutionContext:
    return ResolutionContext(
        timestamp=TIMESTAMP,
        reference_price=reference_price,
        usable_cash=cash,
        current_quantity=current_quantity,
        portfolio_value=portfolio_value,
    )


def make_quantity_resolver(
    *,
    capped_quantity: int = 0,
) -> tuple[QuantityResolver, Mock]:
    capper = Mock(spec=BuyQuantityCapper)
    capper.cap.return_value = capped_quantity
    return QuantityResolver(capper), capper


def make_buffer_quantity_resolver(
    *,
    requested_quantity: int,
    capped_quantity: int,
    buffer_rate: float,
) -> tuple[BufferQuantityResolver, Mock, Mock]:
    resolver = Mock(spec=QuantityResolver)
    resolver.resolve_quantity.return_value = requested_quantity
    capper = Mock(spec=BuyQuantityCapper)
    capper.cap.return_value = capped_quantity
    buffered_resolver = BufferQuantityResolver(resolver, capper, buffer_rate)
    return buffered_resolver, resolver, capper


def instruction(mode: SizingMode, value: int | float | None) -> SizingInstruction:
    return SizingInstruction(mode=mode, value=value)


def test_resolution_context_stores_the_portfolio_snapshot() -> None:
    context = make_context()

    assert context == ResolutionContext(
        timestamp=TIMESTAMP,
        reference_price=100.0,
        usable_cash=1_000.0,
        current_quantity=10,
        portfolio_value=2_000.0,
    )


def test_estimate_buy_cost_includes_slippage_and_commission() -> None:
    execution_model = Mock(spec=ExecutionModel)
    execution_model.calculate_fill_price.return_value = 101.0
    commission_model = Mock(spec=CommissionModel)
    commission_model.calculate.return_value = 20.2
    estimator = ExecutionCostCalculator(
        execution_model=execution_model,
        commission_model=commission_model,
    )

    cost = estimator.estimate_buy_cost(quantity=10, reference_price=100.0)

    assert cost == pytest.approx(1_030.2)
    execution_model.calculate_fill_price.assert_called_once_with(100.0, Side.BUY)
    commission_model.calculate.assert_called_once_with(10, 101.0)


def test_estimate_sell_cost_returns_commission_at_the_sell_fill_price() -> None:
    execution_model = Mock(spec=ExecutionModel)
    execution_model.calculate_fill_price.return_value = 99.0
    commission_model = Mock(spec=CommissionModel)
    commission_model.calculate.return_value = 19.8
    estimator = ExecutionCostCalculator(
        execution_model=execution_model,
        commission_model=commission_model,
    )

    cost = estimator.estimate_sell_cost(quantity=10, reference_price=100.0)

    assert cost == pytest.approx(19.8)
    execution_model.calculate_fill_price.assert_called_once_with(100.0, Side.SELL)
    commission_model.calculate.assert_called_once_with(10, 99.0)


def test_buy_quantity_capper_returns_the_largest_affordable_quantity() -> None:
    cost_calculator = Mock(spec=ExecutionCostCalculator)
    cost_calculator.estimate_buy_cost.side_effect = (
        lambda quantity, reference_price: quantity * reference_price
    )
    capper = BuyQuantityCapper(cost_calculator)

    quantity = capper.cap(
        budget=1_000.0,
        reference_price=100.0,
        max_quantity=None,
    )

    assert quantity == 10


def test_buy_quantity_capper_accounts_for_execution_costs() -> None:
    cost_calculator = Mock(spec=ExecutionCostCalculator)
    cost_calculator.estimate_buy_cost.side_effect = (
        lambda quantity, _reference_price: quantity * 101.0 + 1.0
    )
    capper = BuyQuantityCapper(cost_calculator)

    quantity = capper.cap(
        budget=1_000.0,
        reference_price=100.0,
        max_quantity=None,
    )

    assert quantity == 9


def test_buy_quantity_capper_respects_max_quantity() -> None:
    cost_calculator = Mock(spec=ExecutionCostCalculator)
    cost_calculator.estimate_buy_cost.side_effect = (
        lambda quantity, reference_price: quantity * reference_price
    )
    capper = BuyQuantityCapper(cost_calculator)

    quantity = capper.cap(
        budget=1_000.0,
        reference_price=100.0,
        max_quantity=3,
    )

    assert quantity == 3


def test_buy_quantity_capper_returns_zero_when_one_unit_is_unaffordable() -> None:
    cost_calculator = Mock(spec=ExecutionCostCalculator)

    def estimate_buy_cost(quantity: int, reference_price: float) -> float:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        return quantity * reference_price + 1.0

    cost_calculator.estimate_buy_cost.side_effect = estimate_buy_cost
    capper = BuyQuantityCapper(cost_calculator)

    quantity = capper.cap(
        budget=100.0,
        reference_price=100.0,
        max_quantity=None,
    )

    assert quantity == 0


def test_all_in_buy_uses_cash_as_the_affordability_budget() -> None:
    resolver, capper = make_quantity_resolver(capped_quantity=9)
    sizing_instruction = instruction(SizingMode.ALL_IN, None)
    context = make_context(cash=1_000.0, reference_price=100.0)

    quantity = resolver.resolve_quantity(
        Side.BUY,
        sizing_instruction,
        context,
    )

    assert quantity == 9
    capper.cap.assert_called_once_with(1_000.0, 100.0, None)


def test_all_in_buy_preserves_zero_result_from_capper() -> None:
    resolver, capper = make_quantity_resolver(capped_quantity=0)

    quantity = resolver.resolve_quantity(
        Side.BUY,
        instruction(SizingMode.ALL_IN, None),
        make_context(cash=100.0, reference_price=100.0),
    )

    assert quantity == 0
    capper.cap.assert_called_once_with(100.0, 100.0, None)


@pytest.mark.parametrize("buffer_rate", [-0.01, 1.0, 1.01])
def test_buffer_quantity_resolver_rejects_invalid_buffer_rate(
    buffer_rate: float,
) -> None:
    with pytest.raises(
        ValueError,
        match=r"buffer_rate.*\[0, 1\)",
    ):
        make_buffer_quantity_resolver(
            requested_quantity=10,
            capped_quantity=10,
            buffer_rate=buffer_rate,
        )


def test_buffer_quantity_resolver_accepts_zero_as_an_integer() -> None:
    resolver, base_resolver, capper = make_buffer_quantity_resolver(
        requested_quantity=10,
        capped_quantity=10,
        buffer_rate=0,
    )
    sizing_instruction = instruction(SizingMode.ALL_IN, None)
    context = make_context(cash=1_000.0, reference_price=100.0)

    quantity = resolver.resolve_quantity(
        Side.BUY,
        sizing_instruction,
        context,
    )

    assert quantity == 10
    base_resolver.resolve_quantity.assert_called_once_with(
        Side.BUY,
        sizing_instruction,
        context,
    )
    capper.cap.assert_called_once_with(
        budget=1_000.0,
        reference_price=100.0,
        max_quantity=10,
    )


def test_all_in_buy_passes_buffered_cash_to_capper() -> None:
    resolver, _, capper = make_buffer_quantity_resolver(
        requested_quantity=16,
        capped_quantity=12,
        buffer_rate=0.25,
    )

    quantity = resolver.resolve_quantity(
        Side.BUY,
        instruction(SizingMode.ALL_IN, None),
        make_context(cash=1_000.0, reference_price=60.0),
    )

    assert quantity == 12
    capper.cap.assert_called_once_with(
        budget=750.0,
        reference_price=60.0,
        max_quantity=16,
    )


def test_percent_buy_uses_the_requested_fraction_of_available_cash() -> None:
    resolver, capper = make_quantity_resolver(capped_quantity=4)

    quantity = resolver.resolve_quantity(
        Side.BUY,
        instruction(SizingMode.PERCENT, 0.5),
        make_context(cash=1_000.0, reference_price=120.0),
    )

    assert quantity == 4
    capper.cap.assert_called_once_with(500.0, 120.0, None)


@pytest.mark.parametrize(
    ("percent", "requested_quantity", "expected_quantity"),
    [(0.5, 8, 8), (0.9, 15, 12)],
)
def test_percent_buy_passes_buffer_budget_and_requested_quantity_to_capper(
    percent: float,
    requested_quantity: int,
    expected_quantity: int,
) -> None:
    resolver, _, capper = make_buffer_quantity_resolver(
        requested_quantity=requested_quantity,
        capped_quantity=expected_quantity,
        buffer_rate=0.25,
    )

    quantity = resolver.resolve_quantity(
        Side.BUY,
        instruction(SizingMode.PERCENT, percent),
        make_context(cash=1_000.0, reference_price=60.0),
    )

    assert quantity == expected_quantity
    capper.cap.assert_called_once_with(
        budget=750.0,
        reference_price=60.0,
        max_quantity=requested_quantity,
    )


def test_up_to_buy_passes_requested_max_quantity_to_capper() -> None:
    resolver, capper = make_quantity_resolver(capped_quantity=3)

    quantity = resolver.resolve_quantity(
        Side.BUY,
        instruction(SizingMode.UP_TO, 3),
        make_context(cash=1_000.0, reference_price=100.0),
    )

    assert quantity == 3
    capper.cap.assert_called_once_with(1_000.0, 100.0, 3)


def test_up_to_buy_uses_available_cash_as_the_affordability_budget() -> None:
    resolver, capper = make_quantity_resolver(capped_quantity=4)

    quantity = resolver.resolve_quantity(
        Side.BUY,
        instruction(SizingMode.UP_TO, 20),
        make_context(cash=450.0, reference_price=100.0),
    )

    assert quantity == 4
    capper.cap.assert_called_once_with(450.0, 100.0, 20)


def test_fixed_buy_returns_the_requested_quantity_without_affordability_capping() -> None:
    resolver, capper = make_quantity_resolver()

    quantity = resolver.resolve_quantity(
        Side.BUY,
        instruction(SizingMode.FIXED, 12),
        make_context(cash=100.0, reference_price=100.0),
    )

    assert quantity == 12
    capper.cap.assert_not_called()


def test_fixed_buy_is_capped_against_the_buffered_budget() -> None:
    resolver, _, capper = make_buffer_quantity_resolver(
        requested_quantity=20,
        capped_quantity=12,
        buffer_rate=0.25,
    )

    quantity = resolver.resolve_quantity(
        Side.BUY,
        instruction(SizingMode.FIXED, 20),
        make_context(cash=1_000.0, reference_price=60.0),
    )

    assert quantity == 12
    capper.cap.assert_called_once_with(
        budget=750.0,
        reference_price=60.0,
        max_quantity=20,
    )


@pytest.mark.parametrize(
    ("sizing_instruction", "expected_quantity"),
    [
        pytest.param(instruction(SizingMode.FIXED, 12), 12, id="fixed"),
        pytest.param(instruction(SizingMode.ALL_IN, None), 10, id="all-in"),
        pytest.param(instruction(SizingMode.UP_TO, 6), 6, id="up-to-below-position"),
        pytest.param(instruction(SizingMode.UP_TO, 15), 10, id="up-to-above-position"),
        pytest.param(instruction(SizingMode.PERCENT, 0.25), 2, id="percent"),
    ],
)
def test_sell_quantity_resolves_each_sizing_mode(
    sizing_instruction: SizingInstruction,
    expected_quantity: int,
) -> None:
    resolver, capper = make_quantity_resolver()

    quantity = resolver.resolve_quantity(
        Side.SELL,
        sizing_instruction,
        make_context(current_quantity=10),
    )

    assert quantity == expected_quantity
    capper.cap.assert_not_called()


def test_resolve_quantity_rejects_unknown_side() -> None:
    resolver, capper = make_quantity_resolver()

    with pytest.raises(ValueError, match="invalid side"):
        resolver.resolve_quantity(  # type: ignore[arg-type]
            "buy",
            instruction(SizingMode.ALL_IN, None),
            make_context(),
        )

    capper.cap.assert_not_called()


@pytest.mark.parametrize("side", [Side.BUY, Side.SELL])
def test_resolve_quantity_rejects_unknown_sizing_mode(side: Side) -> None:
    resolver, capper = make_quantity_resolver()
    invalid_instruction = Mock(spec=SizingInstruction)
    invalid_instruction.mode = "invalid"

    with pytest.raises(ValueError, match="Invalid sizing instruction"):
        resolver.resolve_quantity(side, invalid_instruction, make_context())

    capper.cap.assert_not_called()


def test_order_resolver_builds_an_order_from_the_resolved_quantity() -> None:
    quantity_resolver = Mock(spec=QuantityResolver)
    quantity_resolver.resolve_quantity.return_value = 7
    resolver = OrderResolver(quantity_resolver)
    sizing_instruction = instruction(SizingMode.FIXED, 7)
    intent = OrderIntent(
        symbol="AAPL",
        side=Side.BUY,
        timestamp=TIMESTAMP - timedelta(days=1),
        sizing_instruction=sizing_instruction,
    )
    context = make_context()

    order = resolver.resolve(intent, context)

    assert order == Order(
        symbol="AAPL",
        side=Side.BUY,
        signal_timestamp=TIMESTAMP - timedelta(days=1),
        submitted_timestamp=TIMESTAMP,
        quantity=7,
    )
    quantity_resolver.resolve_quantity.assert_called_once_with(
        Side.BUY,
        sizing_instruction,
        context,
    )


@pytest.mark.parametrize("quantity", [0, -1])
def test_order_resolver_returns_none_for_non_positive_quantity(quantity: int) -> None:
    quantity_resolver = Mock(spec=QuantityResolver)
    quantity_resolver.resolve_quantity.return_value = quantity
    resolver = OrderResolver(quantity_resolver)
    intent = OrderIntent(
        symbol="AAPL",
        side=Side.SELL,
        timestamp=TIMESTAMP,
        sizing_instruction=instruction(SizingMode.ALL_IN, None),
    )

    order = resolver.resolve(intent, make_context(current_quantity=0))

    assert order is None
