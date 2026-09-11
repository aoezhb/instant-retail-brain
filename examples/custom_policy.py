from __future__ import annotations

import json

from ird.policies import SafetyStockPolicy
from ird.registry import ComponentAsset, get_policy, register_policy


class ConservativeSafetyStockPolicy(SafetyStockPolicy):
    """Example extension that uses no additional safety-stock days."""

    def __init__(self, safety_stock_days: float = 0.0) -> None:
        super().__init__(safety_stock_days=safety_stock_days)

    def describe(self) -> dict[str, str]:
        return {
            "name": "conservative_safety_stock",
            "version": "0.1.0",
            "task": "replenishment",
            "safety_stock_days": str(self.safety_stock_days),
            "limitation": "Example-only policy with lower inventory protection.",
        }


register_policy(
    "conservative_safety_stock",
    ConservativeSafetyStockPolicy,
    ComponentAsset(
        "policy", "conservative_safety_stock", "0.1.0",
        "ModelOutput+BusinessState+DecisionConstraints", "Decision",
        ("safety_stock_days",), "Example extension; not production calibrated.",
    ),
)


if __name__ == "__main__":
    policy = get_policy("conservative_safety_stock")
    print(json.dumps(policy.describe(), indent=2))
