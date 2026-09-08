from dataclasses import dataclass
from math import isfinite

from backtester.sizing.policy import SizingPlan

@dataclass(frozen=True)
class AssetAllocation:
    allocations: dict[str, float]

    def __post_init__(self):
        if any(weight < 0 or weight > 1 or not isfinite(weight) for weight in self.allocations.values()):
            raise ValueError("Allocation weights must be finite numbers in [0, 1]")

        if sum(weight for weight in self.allocations.values()) > 1:
            raise ValueError("Allocation weights cannot exceed 1")
