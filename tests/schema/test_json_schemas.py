from __future__ import annotations

import json
import unittest
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:
    Draft202012Validator = None
    FormatChecker = None

from ird.cli import run_demo
from ird.data import make_synthetic_dataset
from ird.schema import ApprovalRecord


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


@unittest.skipIf(Draft202012Validator is None, "install the test extra for schema validation")
class JsonSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = Path(__file__).parents[2] / "data" / "schemas"

    def _schema(self, name: str) -> dict[str, Any]:
        return json.loads((self.schemas / name).read_text(encoding="utf-8"))

    def _validate(self, instance: Any, schema: dict[str, Any]) -> None:
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        validator.validate(instance)

    def test_dataset_records_match_public_schemas(self) -> None:
        dataset = make_synthetic_dataset()
        cases = (
            (dataset.demand_records, "demand_record.schema.json"),
            (dataset.inventory_records, "inventory_record.schema.json"),
            (dataset.covariate_records, "covariate_record.schema.json"),
            (dataset.store_node_bindings, "store_node_binding.schema.json"),
        )
        for records, schema_name in cases:
            schema = self._schema(schema_name)
            for record in records:
                self._validate(_json_value(asdict(record)), schema)

    def test_run_record_and_nested_outputs_match_public_schemas(self) -> None:
        payload = run_demo()
        approval = ApprovalRecord(
            payload["decisions"][0]["decision_id"],
            "approved",
            "schema-test",
            datetime(2026, 1, 15, tzinfo=timezone.utc),
        )
        self._validate(_json_value(asdict(approval)), self._schema("approval_record.schema.json"))
        for decision in payload["decisions"]:
            self._validate(decision, self._schema("decision.schema.json"))
        for receipt in payload["receipts"]:
            self._validate(receipt, self._schema("execution_receipt.schema.json"))
        self._validate(payload["model_output"], self._schema("model_output.schema.json"))

        run_schema = self._schema("run_record.schema.json")
        run_schema["properties"]["decisions"]["items"] = self._schema("decision.schema.json")
        run_schema["properties"]["approvals"]["items"] = self._schema("approval_record.schema.json")
        run_schema["properties"]["receipts"]["items"] = self._schema("execution_receipt.schema.json")
        run_schema["properties"]["model_output"] = self._schema("model_output.schema.json")
        self._validate(payload, run_schema)


if __name__ == "__main__":
    unittest.main()
