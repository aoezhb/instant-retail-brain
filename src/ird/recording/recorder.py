from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from ..schema import (
    ApprovalRecord,
    Decision,
    DecisionConstraints,
    ExecutionReceipt,
    ModelOutput,
    RetailDataset,
)


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


class RunRecorder:
    def __init__(
        self,
        run_id: str,
        dataset: RetailDataset,
        state_dataset: RetailDataset | None = None,
    ) -> None:
        self.run_id = run_id
        self.dataset = dataset
        self.state_dataset = state_dataset or dataset
        self.payload: dict[str, Any] | None = None

    def record(
        self,
        model_metadata: Mapping[str, str],
        policy_metadata: Mapping[str, str],
        constraints: DecisionConstraints,
        decisions: list[Decision],
        receipts: list[ExecutionReceipt],
        metrics: Mapping[str, float],
        model_output: ModelOutput | None = None,
        approvals: list[ApprovalRecord] | None = None,
    ) -> None:
        self.payload = {
            "run_id": self.run_id,
            "dataset": {
                "dataset_id": self.dataset.dataset_id,
                "version": self.dataset.version,
                "snapshot_time": self.dataset.snapshot_time.isoformat(),
                "quality": _json_value(asdict(self.dataset.quality)),
            },
            "decision_state_dataset": {
                "dataset_id": self.state_dataset.dataset_id,
                "version": self.state_dataset.version,
                "snapshot_time": self.state_dataset.snapshot_time.isoformat(),
            },
            "model": dict(model_metadata),
            "policy": dict(policy_metadata),
            "constraints": _json_value(asdict(constraints)),
            "decisions": [_json_value(asdict(decision)) for decision in decisions],
            "receipts": [_json_value(asdict(receipt)) for receipt in receipts],
            "approvals": [
                _json_value(asdict(approval)) for approval in (approvals or [])
            ],
            "metrics": dict(metrics),
        }
        if model_output is not None:
            self.payload["model_output"] = {
                "model_name": model_output.model_name,
                "model_version": model_output.model_version,
                "generated_at": model_output.generated_at.isoformat(),
                "forecast_scope": model_output.forecast_scope,
                "horizon_days": model_output.horizon_days,
                "forecast_semantics": model_output.forecast_semantics,
                "input_snapshot_version": model_output.input_snapshot_version,
                "items": [
                    {
                        "business_unit_id": item[0],
                        "store_id": item[1],
                        "node_id": item[2],
                        "sku_id": item[3],
                        "point_forecast": round(forecast, 4),
                        "quantiles": {
                            str(quantile): round(value, 4)
                            for quantile, value in model_output.quantiles.get(item, {}).items()
                        },
                    }
                    for item, forecast in sorted(model_output.forecasts.items())
                ],
            }

    def as_dict(self) -> dict[str, Any]:
        if self.payload is None:
            raise RuntimeError("record must be called before reading the run")
        return self.payload

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")
