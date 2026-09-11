from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timezone
from importlib.util import find_spec
from unittest.mock import patch

from ird.data import make_business_states, make_synthetic_dataset
from ird.cli import run_demo
from ird.models import (
    CovariateQuantileDemandModel,
    HoltTrendDemandModel,
    LightGBMDemandModel,
)
from ird.policies import (
    ExpiryMarkdownPolicy,
    QuantileReplenishmentPolicy,
    RiskAdjustedAssortmentPolicy,
    StoreRiskPolicy,
)
from ird.registry import list_components
from ird.schema import DecisionConstraints


class ExtensionTests(unittest.TestCase):
    def test_covariates_probability_and_advanced_models(self) -> None:
        as_of = datetime(2026, 1, 15, tzinfo=timezone.utc)
        dataset = make_synthetic_dataset(days=14, snapshot_time=as_of)
        probabilistic = CovariateQuantileDemandModel()
        probabilistic.fit(dataset)
        output = probabilistic.predict(dataset, as_of)
        trend = HoltTrendDemandModel()
        trend.fit(dataset)
        trend_output = trend.predict(dataset, as_of)

        item = dataset.items[0]
        self.assertTrue(dataset.covariates_for(item, day=as_of.date(), available_at=as_of))
        self.assertLess(output.quantiles[item][0.1], output.quantiles[item][0.9])
        self.assertGreater(trend_output.forecasts[item], 0)
        decisions = QuantileReplenishmentPolicy().decide(
            output, make_business_states(dataset), DecisionConstraints(service_level=0.9)
        )
        self.assertTrue(decisions)
        self.assertIn("covariate_quantile", list_components()["models"])
        demo = run_demo("covariate_quantile", "quantile_replenishment")
        self.assertTrue(demo["model_output"]["items"][0]["quantiles"])

    def test_lightgbm_adapter_produces_point_and_quantile_outputs(self) -> None:
        class FakeRegressor:
            def __init__(self, **parameters) -> None:
                self.parameters = parameters
                self.value = 0.0

            def fit(self, features, targets, **kwargs) -> None:
                self.value = sum(targets) / len(targets)

            def predict(self, features):
                alpha = self.parameters.get("alpha")
                offset = 0.0 if alpha is None else alpha - 0.5
                return [self.value + offset for _ in features]

        as_of = datetime(2026, 1, 15, tzinfo=timezone.utc)
        dataset = make_synthetic_dataset(days=14, snapshot_time=as_of)
        model = LightGBMDemandModel(n_estimators=10)
        with patch.object(model, "_load_regressor", return_value=FakeRegressor):
            model.fit(dataset)
            output = model.predict(dataset, as_of)

        item = dataset.items[0]
        self.assertGreater(output.forecasts[item], 0)
        self.assertLessEqual(output.quantiles[item][0.1], output.quantiles[item][0.9])
        self.assertIn("lightgbm", list_components()["models"])
        if find_spec("lightgbm") is not None:
            actual = LightGBMDemandModel(n_estimators=5)
            actual.fit(dataset)
            self.assertTrue(actual.predict(dataset, as_of).quantiles[item])

    def test_assortment_and_expiry_policies(self) -> None:
        as_of = datetime(2026, 1, 15, tzinfo=timezone.utc)
        dataset = make_synthetic_dataset(days=14, snapshot_time=as_of)
        model = HoltTrendDemandModel()
        model.fit(dataset)
        output = model.predict(dataset, as_of)
        states = make_business_states(dataset)
        expiring = replace(
            states[0], available_inventory=40, on_order=0, reserved_inventory=0,
            days_to_expiry=1,
        )
        recovered = replace(
            states[0], selling_price=5.0, regular_price=6.0, days_to_expiry=10
        )

        assortment = RiskAdjustedAssortmentPolicy().decide(
            output, states, DecisionConstraints()
        )
        markdown = ExpiryMarkdownPolicy().decide(
            output, [expiring], DecisionConstraints(max_units=100)
        )
        recovery = ExpiryMarkdownPolicy().decide(
            output, [recovered], DecisionConstraints()
        )
        store_risk = StoreRiskPolicy().decide(
            output, [expiring, states[1]], DecisionConstraints()
        )

        self.assertEqual(len(assortment), len(states))
        self.assertTrue(all(decision.approval_required for decision in assortment))
        self.assertEqual(markdown[0].recommended_action, "markdown")
        self.assertGreaterEqual(
            markdown[0].expected_effect["recommended_price"], expiring.unit_cost
        )
        self.assertEqual(recovery[0].recommended_action, "restore_price")
        self.assertIn("restore", ExpiryMarkdownPolicy().explain(recovery[0]).lower())
        unknown_expiry = replace(recovered, days_to_expiry=None)
        self.assertFalse(
            ExpiryMarkdownPolicy().decide(output, [unknown_expiry], DecisionConstraints())
        )
        self.assertEqual(store_risk[0].decision_type, "store_risk")
        policies = list_components()["policies"]
        self.assertIn("risk_adjusted_assortment", policies)
        self.assertIn("expiry_markdown", policies)
        self.assertIn("store_risk", policies)


if __name__ == "__main__":
    unittest.main()
