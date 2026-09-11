from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from typing import Any

from .data import make_business_states, make_synthetic_dataset
from .evaluation import evaluate_replay
from .execution import BacktestExecutor
from .models import MovingAverageDemandModel  # noqa: F401 - registers built-in asset
from .policies import SafetyStockPolicy  # noqa: F401 - registers built-in asset
from .recording import RunRecorder
from .registry import get_model, get_policy
from .schema import DecisionConstraints
from .simulation import replay_inventory


def run_demo(model_name: str = "moving_average", policy_name: str = "safety_stock") -> dict[str, Any]:
    as_of = datetime(2026, 1, 15, tzinfo=timezone.utc)
    training_dataset = make_synthetic_dataset(days=14, snapshot_time=as_of)
    evaluation_dataset = make_synthetic_dataset(days=21)
    model = get_model(model_name)
    policy = get_policy(policy_name)
    policy_metadata = policy.describe()
    if policy_metadata.get("task") != "replenishment":
        raise ValueError("the baseline demo only supports replenishment policies")
    model.fit(training_dataset)
    output = model.predict(training_dataset, as_of)
    constraints = DecisionConstraints(max_units=100, max_spend=500, min_order_qty=1)
    proposed = policy.decide(output, make_business_states(training_dataset), constraints)
    batch = BacktestExecutor().execute(proposed, constraints, as_of)
    accepted = list(batch.accepted)
    replay = replay_inventory(
        evaluation_dataset,
        accepted,
        start_day=date(2026, 1, 15),
        initial_inventory_dataset=training_dataset,
    )
    metrics = evaluate_replay(replay, accepted)
    recorder = RunRecorder("demo-run", evaluation_dataset, state_dataset=training_dataset)
    recorder.record(
        model.describe(), policy_metadata, constraints, proposed, list(batch.receipts), metrics,
        model_output=output,
        approvals=list(batch.approvals),
    )
    assert recorder.payload is not None
    return recorder.payload


def main() -> None:
    parser = argparse.ArgumentParser(prog="ird")
    parser.add_argument("command", choices=["demo"], nargs="?", default="demo")
    parser.add_argument("--model", default="moving_average")
    parser.add_argument("--policy", default="safety_stock")
    args = parser.parse_args()
    if args.command == "demo":
        try:
            payload = run_demo(args.model, args.policy)
        except (KeyError, RuntimeError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
