import pytest

from backtester.execution.costs import CommissionModel, NoCommissionModel, FixedCommissionModel, \
    ProportionalCommissionModel


def test_no_commission_model_returns_zero() -> None:
    commission_model = NoCommissionModel()

    commission = commission_model.calculate(quantity=10, fill_price=20.0)

    assert commission == 0.0


@pytest.mark.parametrize("commission", [0.0, 2.50])
def test_fixed_commission_model_returns_configured_amount(commission: float) -> None:
    commission_model = FixedCommissionModel(commission=commission)

    calculated_commission = commission_model.calculate(
        quantity=10,
        fill_price=20.0,
    )

    assert calculated_commission == pytest.approx(commission)


def test_fixed_commission_model_rejects_negative_commission() -> None:
    with pytest.raises(ValueError, match="Non-negative commission is required"):
        FixedCommissionModel(commission=-0.01)


@pytest.mark.parametrize("commission", [float("inf"), float("-inf"), float("nan")])
def test_fixed_commission_model_rejects_non_finite_commission(commission: float) -> None:
    with pytest.raises(ValueError, match="Commission must be a finite number"):
        FixedCommissionModel(commission)


def test_proportional_commission_model_uses_trade_notional() -> None:
    commission_model = ProportionalCommissionModel(percent=0.015)

    commission = commission_model.calculate(quantity=10, fill_price=20.0)

    assert commission == pytest.approx(3.0)


@pytest.mark.parametrize(
    ("percent", "expected_commission"),
    [
        (0.0, 0.0),
        (1.0, 200.0),
    ],
)
def test_proportional_commission_model_accepts_percentage_boundaries(
    percent: float,
    expected_commission: float,
) -> None:
    commission_model = ProportionalCommissionModel(percent=percent)

    commission = commission_model.calculate(quantity=10, fill_price=20.0)

    assert commission == pytest.approx(expected_commission)


@pytest.mark.parametrize("percent", [-0.01, 1.01])
def test_proportional_commission_model_rejects_percentage_outside_valid_range(
    percent: float,
) -> None:
    with pytest.raises(ValueError, match="percent must be between 0 and 1"):
        ProportionalCommissionModel(percent=percent)


@pytest.mark.parametrize(
    "commission_model",
    [
        pytest.param(NoCommissionModel(), id="no-commission"),
        pytest.param(FixedCommissionModel(commission=1.0), id="fixed"),
        pytest.param(ProportionalCommissionModel(percent=0.01), id="proportional"),
    ],
)
@pytest.mark.parametrize("quantity", [0, -1])
def test_commission_models_reject_non_positive_quantity(
    commission_model: CommissionModel,
    quantity: int,
) -> None:
    with pytest.raises(ValueError, match="quantity must be positive"):
        commission_model.calculate(quantity=quantity, fill_price=20.0)


@pytest.mark.parametrize(
    "commission_model",
    [
        pytest.param(NoCommissionModel(), id="no-commission"),
        pytest.param(FixedCommissionModel(commission=1.0), id="fixed"),
        pytest.param(ProportionalCommissionModel(percent=0.01), id="proportional"),
    ],
)
@pytest.mark.parametrize("fill_price", [0.0, -20.0])
def test_commission_models_reject_non_positive_fill_price(
    commission_model: CommissionModel,
    fill_price: float,
) -> None:
    with pytest.raises(ValueError, match="fill_price must be positive"):
        commission_model.calculate(quantity=10, fill_price=fill_price)
