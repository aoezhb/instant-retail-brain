from __future__ import annotations

import unittest
from datetime import datetime, timezone

from ird.data import make_business_states, make_synthetic_dataset
from ird.models import MovingAverageDemandModel
from ird.policies import SafetyStockPolicy
from ird.registry import (
    ComponentAsset,
    get_model,
    get_policy,
    list_assets,
    register_asset,
    register_model,
    register_policy,
)
from ird.schema import DecisionConstraints, ModelOutput


class ModelPolicyRegistryTests(unittest.TestCase):
    def test_moving_average_ignores_unavailable_observations(self) -> None:
        dataset = make_synthetic_dataset()
        model = MovingAverageDemandModel(window=7)
        model.fit(dataset)
        output = model.predict(dataset, datetime(2026, 1, 22, tzinfo=timezone.utc))
        self.assertEqual(output.input_snapshot_version, dataset.version)
        self.assertGreater(
            output.forecasts[("hq-001", "store-001", "node-001", "sku-milk")], 0
        )
        with self.assertRaisesRegex(ValueError, "snapshot is after"):
            model.predict(dataset, datetime(2026, 1, 15, tzinfo=timezone.utc))

    def test_policy_uses_inventory_position_and_constraints(self) -> None:
        dataset = make_synthetic_dataset()
        model = MovingAverageDemandModel()
        model.fit(dataset)
        output = model.predict(dataset, dataset.snapshot_time)
        constraints = DecisionConstraints(max_units=10, max_spend=30, min_order_qty=1)
        decisions = SafetyStockPolicy().decide(output, make_business_states(dataset), constraints)
        self.assertTrue(decisions)
        self.assertTrue(all(d.quantity <= 10 and d.estimated_spend <= 30 for d in decisions))
        self.assertIn("inventory_position", decisions[0].action_context)

    def test_assets_and_custom_components_share_registry_interface(self) -> None:
        class ConstantModel:
            def __init__(self, value: float = 1.0) -> None:
                self.value = value

            def fit(self, dataset) -> None:
                pass

            def predict(self, dataset, as_of) -> ModelOutput:
                return ModelOutput("test_constant_model", "0.1.0", dataset.version, as_of, "store", {}, 1)

            def describe(self):
                return {"name": "test_constant_model"}

        class NoopPolicy:
            def decide(self, model_output, states, constraints):
                return []

            def explain(self, decision):
                return "noop"

            def describe(self):
                return {"name": "test_noop_policy"}

        register_model(
            "test_constant_model",
            ConstantModel,
            ComponentAsset("model", "test_constant_model", "0.1.0", "RetailDataset", "ModelOutput", ("value",), "test"),
        )
        register_policy(
            "test_noop_policy",
            NoopPolicy,
            ComponentAsset("policy", "test_noop_policy", "0.1.0", "ModelOutput", "Decision", (), "test"),
        )
        self.assertEqual(get_model("test_constant_model", value=2).value, 2)
        self.assertIsInstance(get_policy("test_noop_policy"), NoopPolicy)
        self.assertEqual({asset.category for asset in list_assets()}, {"dataset", "model", "policy", "scenario"})
        self.assertTrue(all(asset.version == "0.1.0" for asset in list_assets()))

        with self.assertRaises(TypeError):
            register_policy(
                "invalid_policy",
                object,
                ComponentAsset("policy", "invalid_policy", "0.1.0", "ModelOutput", "Decision", (), "test"),
            )

    def test_registry_failure_does_not_leave_partial_component(self) -> None:
        class ProbeModel:
            def fit(self, dataset) -> None:
                pass

            def predict(self, dataset, as_of):
                return None

            def describe(self):
                return {}

        asset = ComponentAsset(
            "model", "atomicity_probe", "0.1.0",
            "RetailDataset", "ModelOutput", (), "test",
        )
        register_asset(asset)
        with self.assertRaisesRegex(ValueError, "asset already registered"):
            register_model("atomicity_probe", ProbeModel, asset)
        with self.assertRaisesRegex(KeyError, "unknown model"):
            get_model("atomicity_probe")


if __name__ == "__main__":
    unittest.main()
