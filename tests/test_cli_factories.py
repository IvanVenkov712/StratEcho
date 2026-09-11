from datetime import datetime
from unittest.mock import Mock

import pytest

from backtester.cli.arguments import parse_args
from backtester.cli.factories import (
    create_all_in_all_out_sizing_plan,
    create_commission_model,
    create_execution_model,
    create_order_resolver,
    create_sizing_plan,
    create_strategy,
)
from backtester.domain.trading import (
    OrderIntent,
    PortfolioSnapshot,
    Side,
    SizingInstruction,
    SizingMode,
)
from backtester.execution.costs import (
    ExecutionModel,
    FixedCommissionModel,
    NoCommissionModel,
    ProportionalCommissionModel,
)
from backtester.order_resolving.order_resolver import OrderResolutionContext
from backtester.sizing.policy import SizingPlan
from backtester.sizing.asset_allocation import AssetAllocation

@pytest.mark.parametrize(
    ("arguments", "constructor_name", "expected_arguments"),
    [
        (
            ["--short-window", "10", "--long-window", "40"],
            "SimpleMovingAverageCrossStrategy",
            {"short_window_size": 10, "long_window_size": 40},
        ),
        (
            ["--strategy", "simple-moving-average"],
            "SimpleMovingAverageCrossStrategy",
            {"short_window_size": 20, "long_window_size": 50},
        ),
        (
            ["--strategy", "exponential-moving-average"],
            "ExponentialMovingAverageCrossStrategy",
            {"short_window_size": 20, "long_window_size": 50},
        ),
        (
            ["--strategy", "buy-and-hold"],
            "BuyAndHoldStrategy",
            {},
        ),
        (
            [
                "--strategy",
                "rsi",
                "--rsi-period",
                "10",
                "--rsi-min",
                "25",
                "--rsi-max",
                "75",
            ],
            "CutlerRSIStrategy",
            {"min": 25, "max": 75, "window_size": 10},
        ),
        (
            ["--strategy", "cutler-rsi"],
            "CutlerRSIStrategy",
            {"min": 30.0, "max": 70.0, "window_size": 14},
        ),
        (
            ["--strategy", "exponential-rsi"],
            "ExponentialRSIStrategy",
            {"min": 30.0, "max": 70.0, "window_size": 14},
        ),
        (
            ["--strategy", "wilder-rsi"],
            "WilderRSIStrategy",
            {"min": 30.0, "max": 70.0, "window_size": 14},
        ),
        (
            [
                "--strategy",
                "mean-reversion",
                "--mean-window",
                "15",
                "--mean-threshold",
                "0.9",
            ],
            "SimpleMeanReversionStrategy",
            {"window": 15, "threshold": 0.9},
        ),
        (
            ["--strategy", "simple-mean-reversion"],
            "SimpleMeanReversionStrategy",
            {"window": 20, "threshold": 0.95},
        ),
        (
            ["--strategy", "exponential-mean-reversion"],
            "ExponentialMeanReversionStrategy",
            {"window": 20, "threshold": 0.95},
        ),
        (
            [
                "--strategy",
                "donchian-breakout",
                "--entry-window",
                "55",
                "--exit-window",
                "21",
            ],
            "DonchianBreakoutStrategy",
            {"entry_window": 55, "exit_window": 21},
        ),
    ],
)
def test_create_strategy_passes_cli_parameters_to_concrete_strategy(
    arguments: list[str],
    constructor_name: str,
    expected_arguments: dict[str, int | float],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor = Mock()
    monkeypatch.setattr(
        f"backtester.cli.factories.{constructor_name}",
        constructor,
    )
    args = parse_args(arguments)

    strategy = create_strategy(args.strategy, args)

    constructor.assert_called_once_with(**expected_arguments)
    assert strategy is constructor.return_value


@pytest.mark.parametrize(
    ("arguments", "expected_plan"),
    [
        (
            [],
            SizingPlan(
                buy=SizingInstruction(mode=SizingMode.ALL_IN, value=None),
                sell=SizingInstruction(mode=SizingMode.ALL_IN, value=None),
            ),
        ),
        (
            ["--sizing", "fixed", "--buy-size", "3", "--sell-size", "2"],
            SizingPlan(
                buy=SizingInstruction(mode=SizingMode.FIXED, value=3),
                sell=SizingInstruction(mode=SizingMode.FIXED, value=2),
            ),
        ),
        (
            [
                "--sizing",
                "percent",
                "--buy-percent",
                "0.4",
                "--sell-percent",
                "0.25",
            ],
            SizingPlan(
                buy=SizingInstruction(mode=SizingMode.PERCENT, value=0.4),
                sell=SizingInstruction(mode=SizingMode.PERCENT, value=0.25),
            ),
        ),
    ],
)
def test_create_sizing_plan_uses_selected_policy(
    arguments: list[str],
    expected_plan: SizingPlan,
) -> None:
    args = parse_args(arguments)

    assert create_sizing_plan(args) == expected_plan


def test_create_all_in_all_out_sizing_plan_uses_all_in_for_both_sides() -> None:
    assert create_all_in_all_out_sizing_plan() == SizingPlan(
        buy=SizingInstruction(mode=SizingMode.ALL_IN, value=None),
        sell=SizingInstruction(mode=SizingMode.ALL_IN, value=None),
    )


def test_create_order_resolver_composes_cost_capper_and_cash_buffer() -> None:
    args = parse_args(["--buffer-rate", "0.25"])
    plan = create_sizing_plan(args)
    resolver = create_order_resolver(
        execution_model=ExecutionModel(slippage_rate=0),
        commission_model=NoCommissionModel(),
        buffer_rate=args.buffer_rate,
    )
    context = OrderResolutionContext(
        timestamp=datetime(2024, 1, 2),
        snapshot=PortfolioSnapshot(cash=1_000, positions={"AAPL": 10}, value=1_600),
        reference_prices={"AAPL": 60},
        allocation=AssetAllocation({"AAPL": 1.0}),
    )
    buy_intent = OrderIntent(
        symbol="AAPL",
        side=Side.BUY,
        timestamp=datetime(2024, 1, 1),
        sizing_instruction=plan.buy,
    )
    sell_intent = OrderIntent(
        symbol="AAPL",
        side=Side.SELL,
        timestamp=datetime(2024, 1, 1),
        sizing_instruction=plan.sell,
    )

    assert resolver.resolve(buy_intent, context).quantity == 12
    assert resolver.resolve(sell_intent, context).quantity == 10


@pytest.mark.parametrize(
    ("arguments", "expected_type"),
    [
        ([], NoCommissionModel),
        (
            ["--commission-model", "fixed", "--fixed-commission", "2.50"],
            FixedCommissionModel,
        ),
        (
            [
                "--commission-model",
                "proportional",
                "--commission-rate",
                "0.001",
            ],
            ProportionalCommissionModel,
        ),
    ],
)
def test_create_commission_model_uses_selected_policy(
    arguments: list[str],
    expected_type: type,
) -> None:
    args = parse_args(arguments)

    assert isinstance(create_commission_model(args), expected_type)


def test_create_execution_model_uses_selected_slippage_rate() -> None:
    args = parse_args(["--slippage-rate", "0.01"])

    model = create_execution_model(args)

    assert isinstance(model, ExecutionModel)
    assert model.calculate_fill_price(100, Side.BUY) == pytest.approx(101)
