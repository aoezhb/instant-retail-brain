from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from examples import custom_policy  # noqa: F401 - registers example policy
from ird.cli import run_demo
from ird.data import make_business_states, make_synthetic_dataset
from ird.evaluation import evaluate_replay
from ird.execution import BacktestExecutor, validate_decisions
from ird.models import MovingAverageDemandModel
from ird.policies import SafetyStockPolicy
from ird.recording import RunRecorder
from ird.registry import get_policy
from ird.schema import ApprovalRecord, DecisionConstraints
from ird.simulation import replay_inventory


def build_run():
    dataset = make_synthetic_dataset()
    model = MovingAverageDemandModel()
    model.fit(dataset)
    output = model.predict(dataset, dataset.snapshot_time)
    constraints = DecisionConstraints(max_units=100, max_spend=500)
    policy = SafetyStockPolicy()
    decisions = policy.decide(output, make_business_states(dataset), constraints)
    batch = BacktestExecutor().execute(decisions, constraints, dataset.snapshot_time)
    replay = replay_inventory(dataset, list(batch.accepted))
    metrics = evaluate_replay(replay, batch.accepted)
    return dataset, model, policy, constraints, decisions, batch, replay, metrics


class ReplayAndDemoTests(unittest.TestCase):
    def test_replay_applies_each_order_once_per_item(self) -> None:
        dataset, _, _, _, _, batch, replay, _ = build_run()
        self.assertEqual(replay.ordered_units, round(sum(d.quantity for d in batch.accepted), 2))
        self.assertEqual(len(replay.items), 2)
        duplicate = replace(batch.accepted[0], decision_id="duplicate-order")
        repeated = replay_inventory(dataset, [batch.accepted[0], duplicate])
        self.assertEqual(repeated.ordered_units, round(batch.accepted[0].quantity * 2, 2))

    def test_executor_rejects_invalid_decision(self) -> None:
        dataset, _, _, constraints, decisions, _, _, _ = build_run()
        invalid = replace(decisions[0], quantity=constraints.max_units + 1)
        batch = BacktestExecutor().execute([invalid], constraints, dataset.snapshot_time)
        self.assertFalse(batch.accepted)
        self.assertEqual(batch.receipts[0].status, "rejected")
        below_minimum = replace(
            decisions[0], decision_id="below-minimum", quantity=0.5, estimated_spend=0.5
        )
        batch = BacktestExecutor().execute([below_minimum], constraints, dataset.snapshot_time)
        self.assertFalse(batch.accepted)
        approval_required = replace(
            decisions[0], decision_id="approval-required", approval_required=True
        )
        batch = BacktestExecutor().execute(
            [approval_required], constraints, dataset.snapshot_time
        )
        self.assertFalse(batch.accepted)
        approved = BacktestExecutor().execute(
            [approval_required], constraints, dataset.snapshot_time,
            approvals=[
                ApprovalRecord(
                    approval_required.decision_id,
                    "approved",
                    "test-reviewer",
                    dataset.snapshot_time,
                    "approved for replay",
                )
            ],
        )
        self.assertEqual(approved.accepted, (approval_required,))
        self.assertEqual(approved.approvals[0].decided_by, "test-reviewer")
        rejected_approval = BacktestExecutor().execute(
            [approval_required], constraints, dataset.snapshot_time,
            approvals=[
                ApprovalRecord(
                    approval_required.decision_id,
                    "rejected",
                    "test-reviewer",
                    dataset.snapshot_time,
                )
            ],
        )
        self.assertFalse(rejected_approval.accepted)
        self.assertEqual(rejected_approval.receipts[0].reason, "approval rejected")
        late_approval = BacktestExecutor().execute(
            [approval_required], constraints, dataset.snapshot_time,
            approvals=[
                ApprovalRecord(
                    approval_required.decision_id,
                    "approved",
                    "test-reviewer",
                    datetime(2026, 1, 23, tzinfo=timezone.utc),
                )
            ],
        )
        self.assertFalse(late_approval.accepted)
        self.assertEqual(
            late_approval.receipts[0].reason,
            "approval occurs after execution time",
        )
        expired = replace(
            decisions[0], decision_id="expired",
            expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.assertFalse(validate_decisions([expired], constraints, dataset.snapshot_time))

    def test_executor_enforces_batch_limits_and_known_actions(self) -> None:
        dataset, _, _, constraints, decisions, _, _, _ = build_run()
        first = replace(decisions[0], quantity=6, estimated_spend=400)
        second = replace(
            decisions[0], decision_id="second-order", sku_id="other", quantity=6,
            estimated_spend=400,
        )
        limited = replace(constraints, max_units=10, max_spend=500)
        batch = BacktestExecutor().execute([first, second], limited, dataset.snapshot_time)
        self.assertEqual(batch.accepted, (first,))
        self.assertIn("batch", batch.receipts[1].reason)

        unknown = replace(
            first, decision_id="unknown", decision_type="arbitrary_action",
            recommended_action="anything", quantity=0, estimated_spend=0,
        )
        rejected = BacktestExecutor().execute([unknown], constraints, dataset.snapshot_time)
        self.assertFalse(rejected.accepted)
        self.assertEqual(rejected.receipts[0].reason, "unknown decision type")

        ambiguous_external_write = replace(
            first,
            decision_id="ambiguous-external-write",
            action_context={"external_write": "false"},
        )
        rejected = BacktestExecutor().execute(
            [ambiguous_external_write], constraints, dataset.snapshot_time
        )
        self.assertFalse(rejected.accepted)
        self.assertEqual(
            rejected.receipts[0].reason,
            "external_write flag must be boolean",
        )

        duplicate = replace(first, decision_id=decisions[0].decision_id)
        with self.assertRaisesRegex(ValueError, "duplicate decision_id"):
            BacktestExecutor().execute(
                [decisions[0], duplicate], constraints, dataset.snapshot_time
            )

    def test_recorder_saves_inputs_needed_to_repeat_run(self) -> None:
        dataset, model, policy, constraints, decisions, batch, _, metrics = build_run()
        recorder = RunRecorder("test-run", dataset)
        output = model.predict(dataset, dataset.snapshot_time)
        recorder.record(
            model.describe(), policy.describe(), constraints, decisions,
            list(batch.receipts), metrics, model_output=output,
            approvals=list(batch.approvals),
        )
        payload = recorder.as_dict()
        self.assertEqual(payload["dataset"]["version"], dataset.version)
        self.assertIn("constraints", payload)
        self.assertEqual(len(payload["receipts"]), len(decisions))
        self.assertIn("approvals", payload)
        self.assertEqual(payload["model_output"]["model_name"], output.model_name)
        self.assertEqual(
            payload["model_output"]["input_snapshot_version"], dataset.version
        )

    def test_metrics_include_service_and_cash_indicators(self) -> None:
        *_, metrics = build_run()
        self.assertIn("fill_rate", metrics)
        self.assertIn("committed_spend", metrics)
        self.assertGreaterEqual(metrics["fill_rate"], 0)
        self.assertLessEqual(metrics["fill_rate"], 1)

    def test_demo_runs_full_chain(self) -> None:
        payload = run_demo()
        training = make_synthetic_dataset(
            days=14,
            snapshot_time=datetime(2026, 1, 15, tzinfo=timezone.utc),
        )
        evaluation = make_synthetic_dataset(days=21)
        self.assertEqual(payload["run_id"], "demo-run")
        self.assertEqual(payload["model"]["input_snapshot_version"], training.version)
        self.assertEqual(payload["dataset"]["version"], evaluation.version)
        self.assertEqual(payload["decision_state_dataset"]["version"], training.version)
        self.assertTrue(payload["decisions"])
        self.assertIn("fill_rate", payload["metrics"])

    def test_custom_policy_is_registered_without_changing_demo_flow(self) -> None:
        policy = get_policy("conservative_safety_stock")
        self.assertEqual(policy.describe()["name"], "conservative_safety_stock")
        payload = run_demo(policy_name="conservative_safety_stock")
        self.assertEqual(payload["policy"]["name"], "conservative_safety_stock")

    def test_public_docs_explain_demo_and_production_use(self) -> None:
        root = Path(__file__).parents[2]
        readme = (root / "README.md").read_text(encoding="utf-8")
        architecture = (root / "docs" / "architecture.md").read_text(encoding="utf-8")
        self.assertIn("python -m ird demo", readme)
        self.assertIn("does not cover production deployment", architecture)


if __name__ == "__main__":
    unittest.main()
