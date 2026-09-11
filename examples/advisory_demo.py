from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import datetime, timezone

from ird.data import make_business_states, make_synthetic_dataset
from ird.models import HoltTrendDemandModel
from ird.policies import ExpiryMarkdownPolicy, RiskAdjustedAssortmentPolicy, StoreRiskPolicy
from ird.schema import DecisionConstraints


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def main() -> None:
    as_of = datetime(2026, 1, 15, tzinfo=timezone.utc)
    dataset = make_synthetic_dataset(days=14, snapshot_time=as_of)
    model = HoltTrendDemandModel()
    model.fit(dataset)
    output = model.predict(dataset, as_of)
    states = make_business_states(dataset)
    advisory_states = [
        replace(states[0], available_inventory=40, on_order=0, days_to_expiry=1),
        replace(states[1], selling_price=2.0, regular_price=2.5, days_to_expiry=10),
    ]
    constraints = DecisionConstraints()

    decisions = []
    for policy in (
        RiskAdjustedAssortmentPolicy(),
        ExpiryMarkdownPolicy(),
        StoreRiskPolicy(),
    ):
        decisions.extend(policy.decide(output, advisory_states, constraints))

    print(json.dumps([asdict(decision) for decision in decisions], indent=2, default=_json_default))


if __name__ == "__main__":
    main()
