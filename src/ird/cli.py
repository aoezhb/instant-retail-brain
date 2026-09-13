from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from .data import make_business_states, make_synthetic_dataset
from .evaluation import evaluate_operating_metrics, evaluate_replay, summarize_forecast_metrics
from .execution import BacktestExecutor
from .models import MovingAverageDemandModel  # noqa: F401 - registers built-in asset
from .policies import SafetyStockPolicy  # noqa: F401 - registers built-in asset
from .recording import RunRecorder
from .registry import get_model, get_policy
from .schema import DecisionConstraints
from .schema import DataQualityReport, RetailDataset
from .simulation import replay_inventory


def run_demo(
    model_name: str = "covariate_quantile",
    policy_name: str = "quantile_replenishment",
) -> dict[str, Any]:
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
    ordered_items = sorted(output.forecasts)
    future_actual = [
        sum(record.demand for record in evaluation_dataset.demand_for(item) if record.day >= as_of.date()) / max(1, len([record for record in evaluation_dataset.demand_for(item) if record.day >= as_of.date()]))
        for item in ordered_items
    ]
    predicted = [output.forecasts[item] for item in ordered_items]
    p50 = [output.quantiles.get(item, {}).get(0.5, output.forecasts[item]) for item in ordered_items]
    p90 = [output.quantiles.get(item, {}).get(0.9, output.forecasts[item]) for item in ordered_items]
    metrics.update(summarize_forecast_metrics(future_actual, predicted, p50, p90))
    metrics.update(evaluate_operating_metrics(
        replay, accepted, rejected_decisions=len(batch.receipts) - len(batch.accepted),
        approval_required=sum(decision.approval_required for decision in proposed),
        total_decisions=len(proposed),
    ))
    recorder = RunRecorder("demo-run", evaluation_dataset, state_dataset=training_dataset)
    recorder.record(
        model.describe(), policy_metadata, constraints, proposed, list(batch.receipts), metrics,
        model_output=output,
        approvals=list(batch.approvals),
    )
    assert recorder.payload is not None
    recorder.payload["result_summary"] = _build_result_summary(output, proposed, metrics, batch)
    return recorder.payload


def run_dataset_demo(
    dataset,
    model_name: str = "moving_average",
    policy_name: str = "safety_stock",
) -> dict[str, Any]:
    """Run the same deterministic chain against a caller-provided dataset."""
    training_dataset, evaluation_dataset = _split_dataset_for_demo(dataset)
    model = get_model(model_name)
    policy = get_policy(policy_name)
    if policy.describe().get("task") != "replenishment":
        raise ValueError("the demo only supports replenishment policies")
    model.fit(training_dataset)
    output = model.predict(training_dataset, training_dataset.snapshot_time)
    constraints = DecisionConstraints(max_units=100, max_spend=500, min_order_qty=1)
    proposed = policy.decide(output, make_business_states(training_dataset), constraints)
    batch = BacktestExecutor().execute(proposed, constraints, training_dataset.snapshot_time)
    replay = replay_inventory(evaluation_dataset, list(batch.accepted), start_day=training_dataset.snapshot_time.date() + timedelta(days=1), initial_inventory_dataset=training_dataset)
    metrics = evaluate_replay(replay, batch.accepted)
    ordered_items = sorted(output.forecasts)
    actual_records = [[r for r in evaluation_dataset.demand_for(item) if r.day >= training_dataset.snapshot_time.date() + timedelta(days=1)] for item in ordered_items]
    actual = [sum(r.demand for r in records) / len(records) if records else 0.0 for records in actual_records]
    predicted = [output.forecasts[item] for item in ordered_items]
    p50 = [output.quantiles.get(item, {}).get(0.5, output.forecasts[item]) for item in ordered_items]
    p90 = [output.quantiles.get(item, {}).get(0.9, output.forecasts[item]) for item in ordered_items]
    metrics.update(summarize_forecast_metrics(actual, predicted, p50, p90))
    metrics.update(evaluate_operating_metrics(replay, batch.accepted, len(batch.receipts) - len(batch.accepted), sum(d.approval_required for d in proposed), len(proposed)))
    recorder = RunRecorder("uploaded-demo", evaluation_dataset, state_dataset=training_dataset)
    recorder.record(model.describe(), policy.describe(), constraints, proposed, list(batch.receipts), metrics, model_output=output, approvals=list(batch.approvals))
    assert recorder.payload is not None
    recorder.payload["result_summary"] = _build_result_summary(output, proposed, metrics, batch)
    return recorder.as_dict()


def _split_dataset_for_demo(dataset: RetailDataset) -> tuple[RetailDataset, RetailDataset]:
    days = sorted({record.day for record in dataset.demand_records})
    if len(days) < 2:
        raise ValueError("upload at least two demand days for an out-of-sample demo")
    cutoff_index = max(0, int(len(days) * 0.8) - 1)
    cutoff = days[cutoff_index]
    training_snapshot = datetime.combine(cutoff, time.max, tzinfo=dataset.snapshot_time.tzinfo)
    future_inventory = tuple(
        record for record in dataset.inventory_records
        if record.snapshot_time > training_snapshot
    )
    if future_inventory:
        raise ValueError(
            "inventory snapshot must be on or before the training cutoff; "
            "upload a historical inventory snapshot for time-holdout evaluation"
        )
    training_demands = tuple(
        record for record in dataset.demand_records
        if record.day <= cutoff and record.available_time <= training_snapshot
    )
    evaluation_demands = tuple(record for record in dataset.demand_records if record.day > cutoff)
    training_covariates = tuple(
        record for record in dataset.covariate_records
        if record.day <= cutoff and record.available_time <= training_snapshot
    )
    evaluation_covariates = tuple(record for record in dataset.covariate_records if record.day > cutoff)
    if not evaluation_demands:
        raise ValueError("upload data with a future evaluation window")
    training = replace(
        dataset,
        version=f"{dataset.version}-train",
        snapshot_time=training_snapshot,
        demand_records=training_demands,
        covariate_records=training_covariates,
        quality=DataQualityReport(len(training_demands) + len(dataset.inventory_records) + len(training_covariates), len(training_demands) + len(dataset.inventory_records) + len(training_covariates)),
    )
    evaluation = replace(
        dataset,
        version=f"{dataset.version}-eval",
        demand_records=evaluation_demands,
        covariate_records=evaluation_covariates,
        quality=DataQualityReport(len(evaluation_demands) + len(dataset.inventory_records) + len(evaluation_covariates), len(evaluation_demands) + len(dataset.inventory_records) + len(evaluation_covariates)),
    )
    return training, evaluation


def _build_result_summary(output, proposed, metrics, batch) -> dict[str, Any]:
    items = []
    for item in sorted(output.forecasts):
        decision = next((decision for decision in proposed if (decision.business_unit_id, decision.store_id, decision.node_id, decision.sku_id) == item), None)
        quantiles = output.quantiles.get(item, {})
        items.append({
            "business_unit_id": item[0],
            "store_id": item[1],
            "node_id": item[2],
            "sku_id": item[3],
            "forecast_p50": round(quantiles.get(0.5, output.forecasts[item]), 2),
            "forecast_p90": round(quantiles.get(0.9, output.forecasts[item]), 2),
            "recommended_order_qty": round(decision.quantity, 2) if decision else 0.0,
            "expected_cost": round(decision.estimated_spend, 2) if decision else 0.0,
            "decision_id": decision.decision_id if decision else None,
        })
    accepted_count = len(batch.accepted)
    proposed_count = len(proposed)
    if accepted_count == proposed_count:
        constraint_status = "passed"
    elif accepted_count == 0:
        constraint_status = "rejected"
    else:
        constraint_status = "partial"
    return {
        "aggregate": {
            "forecast_p50": round(sum(item["forecast_p50"] for item in items), 2),
            "forecast_p90": round(sum(item["forecast_p90"] for item in items), 2),
            "recommended_order_qty": round(sum(decision.quantity for decision in proposed), 2),
            "expected_cost": round(sum(decision.estimated_spend for decision in proposed), 2),
            "stockout_risk": round(metrics.get("stockout_rate", 0.0), 4),
            "approval_required": any(decision.approval_required for decision in proposed),
            "constraint_status": constraint_status,
        },
        "items": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="ird")
    parser.add_argument("command", choices=["demo"], nargs="?", default="demo")
    parser.add_argument("--model", default="covariate_quantile")
    parser.add_argument("--policy", default="quantile_replenishment")
    args = parser.parse_args()
    if args.command == "demo":
        try:
            payload = run_demo(args.model, args.policy)
        except (KeyError, RuntimeError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
