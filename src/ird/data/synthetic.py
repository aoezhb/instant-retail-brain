from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from .handler import RetailDataHandler
from ..schema import BusinessState, RetailDataset

SNAPSHOT_TIME = datetime(2026, 1, 22, tzinfo=timezone.utc)


def make_synthetic_rows(days: int = 21) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if days < 7:
        raise ValueError("days must be at least 7")
    start = date(2026, 1, 1)
    demand_rows: list[dict[str, Any]] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        observed_at = datetime.combine(day, time.min, tzinfo=timezone.utc)
        weekend_factor = 1.25 if day.weekday() >= 5 else 1.0
        demand_rows.extend(
            [
                {
                    "business_unit_id": "hq-001", "store_id": "store-001", "node_id": "node-001",
                    "sku_id": "sku-milk", "day": day.isoformat(),
                    "demand": round(5 * weekend_factor + offset % 3 * 0.3, 2),
                    "available": offset not in {13, 14}, "event_time": observed_at.isoformat(),
                    "available_time": observed_at.isoformat(),
                },
                {
                    "business_unit_id": "hq-001", "store_id": "store-001", "node_id": "node-001",
                    "sku_id": "sku-water", "day": day.isoformat(),
                    "demand": round(3 * weekend_factor + offset % 2 * 0.2, 2),
                    "available": True, "event_time": observed_at.isoformat(),
                    "available_time": observed_at.isoformat(),
                },
            ]
        )
    inventory_rows = [
        {
            "business_unit_id": "hq-001", "store_id": "store-001", "node_id": "node-001",
            "sku_id": "sku-milk", "available_inventory": 3, "on_order": 2,
            "reserved_inventory": 1, "backorders": 0, "unit_cost": 4.0,
            "lead_time_days": 2, "review_period_days": 2, "selling_price": 6.0,
            "regular_price": 6.0,
            "days_to_expiry": 2,
        },
        {
            "business_unit_id": "hq-001", "store_id": "store-001", "node_id": "node-001",
            "sku_id": "sku-water", "available_inventory": 10, "on_order": 0,
            "reserved_inventory": 0, "backorders": 0, "unit_cost": 1.5,
            "lead_time_days": 1, "review_period_days": 2, "selling_price": 2.5,
            "regular_price": 2.5,
            "days_to_expiry": 30,
        },
    ]
    return demand_rows, inventory_rows


def make_synthetic_covariate_rows(days: int = 21) -> list[dict[str, Any]]:
    start = date(2026, 1, 1)
    rows: list[dict[str, Any]] = []
    for offset in range(days + 1):
        day = start + timedelta(days=offset)
        event_time = datetime.combine(day, time.min, tzinfo=timezone.utc)
        available_time = event_time - timedelta(hours=12)
        values = {
            "weekend": float(day.weekday() >= 5),
            "promotion": float(offset % 7 == 5),
            "holiday": float(day == date(2026, 1, 1)),
            "temperature": float(8 + offset % 6),
        }
        for sku_id in ("sku-milk", "sku-water"):
            rows.append(
                {
                    "business_unit_id": "hq-001", "store_id": "store-001",
                    "node_id": "node-001", "sku_id": sku_id, "day": day.isoformat(),
                    "values": values, "event_time": event_time.isoformat(),
                    "available_time": available_time.isoformat(),
                }
            )
    return rows


def make_synthetic_dataset(
    days: int = 21,
    snapshot_time: datetime = SNAPSHOT_TIME,
) -> RetailDataset:
    demand_rows, inventory_rows = make_synthetic_rows(days)
    covariate_rows = make_synthetic_covariate_rows(days)
    return RetailDataHandler().build_dataset(
        demand_rows, inventory_rows, snapshot_time, covariate_rows
    )


def make_business_states(dataset: RetailDataset | None = None) -> list[BusinessState]:
    source = dataset or make_synthetic_dataset()
    return [
        BusinessState(
            record.business_unit_id, record.store_id, record.node_id, record.sku_id,
            record.available_inventory, record.on_order, record.reserved_inventory,
            record.backorders, record.unit_cost, record.lead_time_days, record.review_period_days,
            record.selling_price, record.regular_price, record.days_to_expiry,
            source.snapshot_time,
        )
        for record in source.inventory_records
    ]
