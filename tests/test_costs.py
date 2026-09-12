import pytest

from backtester.execution.costs import fits_budget


@pytest.mark.parametrize(
    ("cost", "budget", "expected"),
    [
        pytest.param(0.2, 0.3, True, id="below-budget"),
        pytest.param(0.3, 0.3, True, id="exact-budget"),
        pytest.param(0.1 + 0.2, 0.3, True, id="floating-point-roundoff"),
        pytest.param(0.3 + 5e-10, 0.3, True, id="within-absolute-tolerance"),
        pytest.param(0.3 + 2e-9, 0.3, False, id="outside-absolute-tolerance"),
        pytest.param(1_000_000 + 5e-7, 1_000_000, True, id="within-relative-tolerance"),
        pytest.param(1_000_000 + 2e-6, 1_000_000, False, id="outside-relative-tolerance"),
    ],
)
def test_fits_budget_accepts_only_affordable_costs_or_tolerated_excess(
    cost: float, budget: float, expected: bool,
) -> None:
    assert fits_budget(cost, budget) is expected
