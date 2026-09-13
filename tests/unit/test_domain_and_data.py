from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ird.data import FileDataProvider, RetailDataHandler, make_synthetic_dataset, make_synthetic_rows
from ird.schema import (
    BusinessState,
    BusinessUnit,
    DecisionConstraints,
    FulfillmentNode,
    InventoryRecord,
    Store,
)


class DomainAndDataTests(unittest.TestCase):
    def test_keeps_business_store_and_node_ids_distinct(self) -> None:
        unit = BusinessUnit("hq-001", "Demo HQ")
        store = Store(unit.business_unit_id, "store-001", "Demo Store")
        node = FulfillmentNode(unit.business_unit_id, "node-001", "Demo Node")
        self.assertNotEqual(store.store_id, node.node_id)

    def test_dataset_exposes_snapshot_and_quality_metadata(self) -> None:
        dataset = make_synthetic_dataset()
        self.assertTrue(dataset.quality.passed)
        self.assertTrue(dataset.version)
        self.assertEqual(dataset.inventory_for(dataset.items[0]).node_id, "node-001")
        self.assertEqual(dataset.items[0][0], "hq-001")
        self.assertEqual(len(dataset.store_node_bindings), 1)

    def test_inventory_position_uses_reserved_and_backorders(self) -> None:
        state = BusinessState("hq", "store", "node", "sku", 10, 4, 2, 1, 3, 1, 1)
        self.assertEqual(state.inventory_position, 11)

    def test_domain_objects_enforce_runtime_types_and_timezones(self) -> None:
        with self.assertRaisesRegex(ValueError, "allow_external_write must be boolean"):
            DecisionConstraints(allow_external_write="false")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "lead_time_days must be"):
            InventoryRecord(
                "hq", "store", "node", "sku", 1, 0, 0, 0, 1,
                1.5, 1, datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        with self.assertRaisesRegex(ValueError, "snapshot_time must be timezone-aware"):
            InventoryRecord(
                "hq", "store", "node", "sku", 1, 0, 0, 0, 1,
                1, 1, datetime(2026, 1, 1),
            )

    def test_synthetic_data_is_deterministic(self) -> None:
        first = make_synthetic_rows()
        second = make_synthetic_rows()
        self.assertEqual(first, second)

    def test_file_provider_reads_csv_and_json(self) -> None:
        root = Path(__file__).parents[2] / "data" / "sample"
        demand_rows = FileDataProvider(root / "demand.csv").load()
        inventory_rows = FileDataProvider(root / "inventory.json").load()
        covariate_rows = FileDataProvider(root / "covariates.json").load()
        self.assertEqual(demand_rows[0]["sku_id"], "sku-milk")
        self.assertEqual(inventory_rows[0]["node_id"], "node-001")
        self.assertEqual(covariate_rows[0]["values"]["promotion"], 1)
        dataset = RetailDataHandler().build_dataset(
            demand_rows,
            inventory_rows,
            datetime(2026, 1, 5, tzinfo=timezone.utc),
            covariate_rows,
        )
        self.assertEqual(len(dataset.covariate_records), 2)
        self.assertEqual(dataset.inventory_records[0].selling_price, 6.0)
        schemas = root.parent / "schemas"
        for path in schemas.glob("*.schema.json"):
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["type"], "object")

    def test_handler_rejects_invalid_or_future_data(self) -> None:
        demand_rows, inventory_rows = make_synthetic_rows()
        demand_rows[0] = {**demand_rows[0], "demand": -1}
        with self.assertRaisesRegex(ValueError, "data quality failed"):
            RetailDataHandler().build_dataset(
                demand_rows, inventory_rows, datetime(2026, 1, 22, tzinfo=timezone.utc)
            )
        demand_rows, inventory_rows = make_synthetic_rows()
        demand_rows.append(dict(demand_rows[0]))
        with self.assertRaisesRegex(ValueError, "duplicate demand key"):
            RetailDataHandler().build_dataset(
                demand_rows, inventory_rows, datetime(2026, 1, 22, tzinfo=timezone.utc)
            )

    def test_dataset_separates_demand_and_inventory(self) -> None:
        dataset = make_synthetic_dataset()
        self.assertEqual(len(dataset.items), 2)
        self.assertEqual(len(dataset.inventory_records), 2)
        self.assertGreater(len(dataset.demand_for(dataset.items[0])), 0)

    def test_handler_keeps_business_units_isolated(self) -> None:
        demand_rows, inventory_rows = make_synthetic_rows(days=7)
        second_demands = [
            {**row, "business_unit_id": "hq-002"} for row in demand_rows
        ]
        second_inventory = [
            {**row, "business_unit_id": "hq-002"} for row in inventory_rows
        ]
        dataset = RetailDataHandler().build_dataset(
            demand_rows + second_demands,
            inventory_rows + second_inventory,
            datetime(2026, 1, 22, tzinfo=timezone.utc),
        )
        first = ("hq-001", "store-001", "node-001", "sku-milk")
        second = ("hq-002", "store-001", "node-001", "sku-milk")
        self.assertEqual(len(dataset.demand_for(first)), 7)
        self.assertEqual(len(dataset.demand_for(second)), 7)
        self.assertEqual(dataset.inventory_for(second).business_unit_id, "hq-002")

    def test_handler_rejects_incoherent_or_ambiguous_values(self) -> None:
        demand_rows, inventory_rows = make_synthetic_rows(days=7)
        demand_rows[0] = {**demand_rows[0], "available": "not"}
        with self.assertRaisesRegex(ValueError, "invalid boolean"):
            RetailDataHandler().build_dataset(
                demand_rows, inventory_rows, datetime(2026, 1, 22, tzinfo=timezone.utc)
            )

        demand_rows, inventory_rows = make_synthetic_rows(days=7)
        inventory_rows[0] = {**inventory_rows[0], "sku_id": "unmatched-sku"}
        with self.assertRaisesRegex(ValueError, "missing inventory"):
            RetailDataHandler().build_dataset(
                demand_rows, inventory_rows, datetime(2026, 1, 22, tzinfo=timezone.utc)
            )

        demand_rows, inventory_rows = make_synthetic_rows(days=7)
        demand_rows[0] = {**demand_rows[0], "demand": "NaN"}
        with self.assertRaisesRegex(ValueError, "must be finite"):
            RetailDataHandler().build_dataset(
                demand_rows, inventory_rows, datetime(2026, 1, 22, tzinfo=timezone.utc)
            )

        demand_rows, inventory_rows = make_synthetic_rows(days=7)
        inventory_rows[0] = {**inventory_rows[0], "lead_time_days": 1.5}
        with self.assertRaisesRegex(ValueError, "nonnegative integer"):
            RetailDataHandler().build_dataset(
                demand_rows, inventory_rows, datetime(2026, 1, 22, tzinfo=timezone.utc)
            )


if __name__ == "__main__":
    unittest.main()
