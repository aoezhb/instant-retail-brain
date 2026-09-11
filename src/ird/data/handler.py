from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timezone
from math import isfinite
from typing import Any, Mapping

from ..schema import (
    CovariateRecord,
    DataQualityReport,
    DemandRecord,
    InventoryRecord,
    RetailDataset,
    StoreNodeBinding,
)

DEMAND_FIELDS = ("business_unit_id", "store_id", "node_id", "sku_id", "day", "demand")
INVENTORY_FIELDS = (
    "business_unit_id", "store_id", "node_id", "sku_id", "available_inventory",
    "on_order", "reserved_inventory", "backorders", "unit_cost", "lead_time_days",
    "review_period_days",
)
COVARIATE_FIELDS = (
    "business_unit_id", "store_id", "node_id", "sku_id", "day", "values",
    "event_time", "available_time",
)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def _as_id(row: Mapping[str, Any], field: str) -> str:
    value = str(row[field]).strip()
    if not value:
        raise ValueError(f"{field} cannot be empty")
    return value


def _as_finite_float(value: Any, field: str) -> float:
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError(f"{field} must be finite")
    return parsed


def _as_nonnegative_int(value: Any, field: str) -> int:
    parsed = _as_finite_float(value, field)
    if not parsed.is_integer() or parsed < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return int(parsed)


def _parse_datetime(value: Any, fallback_day: date | None = None) -> datetime:
    if value:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    if fallback_day:
        return datetime.combine(fallback_day, time.min, tzinfo=timezone.utc)
    raise ValueError("datetime value is required")


class RetailDataHandler:
    def build_dataset(
        self,
        demand_rows: list[Mapping[str, Any]],
        inventory_rows: list[Mapping[str, Any]],
        snapshot_time: datetime,
        covariate_rows: list[Mapping[str, Any]] | None = None,
    ) -> RetailDataset:
        if snapshot_time.tzinfo is None or snapshot_time.utcoffset() is None:
            raise ValueError("snapshot_time must be timezone-aware")
        covariate_rows = covariate_rows or []
        errors: list[str] = []
        demands: list[DemandRecord] = []
        inventories: list[InventoryRecord] = []
        covariates: list[CovariateRecord] = []
        demand_keys: set[tuple[str, str, str, str, date]] = set()
        inventory_keys: set[tuple[str, str, str, str]] = set()
        covariate_keys: set[tuple[str, str, str, str, date, datetime]] = set()

        for index, row in enumerate(demand_rows, start=1):
            try:
                missing = [field for field in DEMAND_FIELDS if row.get(field) in (None, "")]
                if missing:
                    raise ValueError(f"missing {','.join(missing)}")
                day = date.fromisoformat(str(row["day"]))
                demand = _as_finite_float(row["demand"], "demand")
                if demand < 0:
                    raise ValueError("demand cannot be negative")
                event_time = _parse_datetime(row.get("event_time"), day)
                available_time = _parse_datetime(row.get("available_time"), day)
                if available_time < event_time:
                    raise ValueError("available_time is before event_time")
                if available_time > snapshot_time:
                    raise ValueError("available_time is after snapshot_time")
                key = (
                    _as_id(row, "business_unit_id"), _as_id(row, "store_id"),
                    _as_id(row, "node_id"), _as_id(row, "sku_id"), day,
                )
                if key in demand_keys:
                    raise ValueError("duplicate demand key")
                demand_keys.add(key)
                demands.append(
                    DemandRecord(
                        key[0], key[1], key[2], key[3], day, demand,
                        _as_bool(row.get("available", True)),
                        event_time, available_time,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                errors.append(f"demand row {index}: {exc}")

        for index, row in enumerate(inventory_rows, start=1):
            try:
                missing = [field for field in INVENTORY_FIELDS if row.get(field) in (None, "")]
                if missing:
                    raise ValueError(f"missing {','.join(missing)}")
                values = {
                    field: _as_finite_float(row[field], field)
                    for field in ("available_inventory", "on_order", "reserved_inventory", "backorders", "unit_cost")
                }
                if any(value < 0 for value in values.values()):
                    raise ValueError("inventory quantities and unit_cost cannot be negative")
                selling_price = _as_finite_float(row.get("selling_price", 0.0), "selling_price")
                regular_price = _as_finite_float(
                    row.get("regular_price", selling_price), "regular_price"
                )
                days_to_expiry = (
                    _as_nonnegative_int(row["days_to_expiry"], "days_to_expiry")
                    if row.get("days_to_expiry") not in (None, "")
                    else None
                )
                if selling_price < 0 or regular_price < 0 or (
                    days_to_expiry is not None and days_to_expiry < 0
                ):
                    raise ValueError("price and days_to_expiry cannot be negative")
                lead_time_days = _as_nonnegative_int(row["lead_time_days"], "lead_time_days")
                review_period_days = _as_nonnegative_int(
                    row["review_period_days"], "review_period_days"
                )
                inventory_snapshot = (
                    _parse_datetime(row["snapshot_time"])
                    if row.get("snapshot_time") not in (None, "")
                    else snapshot_time
                )
                if inventory_snapshot > snapshot_time:
                    raise ValueError("inventory snapshot is after dataset snapshot")
                key = (
                    _as_id(row, "business_unit_id"), _as_id(row, "store_id"),
                    _as_id(row, "node_id"), _as_id(row, "sku_id"),
                )
                if key in inventory_keys:
                    raise ValueError("duplicate inventory key")
                inventory_keys.add(key)
                inventories.append(
                    InventoryRecord(
                        key[0], key[1], key[2], key[3],
                        values["available_inventory"], values["on_order"], values["reserved_inventory"],
                        values["backorders"], values["unit_cost"], lead_time_days,
                        review_period_days, inventory_snapshot,
                        selling_price, regular_price, days_to_expiry,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                errors.append(f"inventory row {index}: {exc}")

        for index, row in enumerate(covariate_rows, start=1):
            try:
                missing = [field for field in COVARIATE_FIELDS if row.get(field) in (None, "")]
                if missing:
                    raise ValueError(f"missing {','.join(missing)}")
                day = date.fromisoformat(str(row["day"]))
                event_time = _parse_datetime(row["event_time"])
                available_time = _parse_datetime(row["available_time"])
                if available_time > snapshot_time:
                    raise ValueError("available_time is after snapshot_time")
                raw_values = row["values"]
                if not isinstance(raw_values, Mapping) or not raw_values:
                    raise ValueError("values must be a non-empty mapping")
                values = {
                    str(name): _as_finite_float(value, f"values.{name}")
                    for name, value in raw_values.items()
                }
                key = (
                    _as_id(row, "business_unit_id"), _as_id(row, "store_id"),
                    _as_id(row, "node_id"), _as_id(row, "sku_id"), day, available_time,
                )
                if key in covariate_keys:
                    raise ValueError("duplicate covariate key")
                covariate_keys.add(key)
                covariates.append(
                    CovariateRecord(
                        key[0], key[1], key[2], key[3], day, values,
                        event_time, available_time,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                errors.append(f"covariate row {index}: {exc}")

        demand_items = {record.item_key for record in demands}
        inventory_items = {record.item_key for record in inventories}
        covariate_items = {record.item_key for record in covariates}
        for item in sorted(demand_items - inventory_items):
            errors.append(f"missing inventory for {item}")
        for item in sorted(inventory_items - demand_items):
            errors.append(f"inventory has no matching demand for {item}")
        for item in sorted(covariate_items - demand_items):
            errors.append(f"covariate has no matching demand for {item}")

        total = len(demand_rows) + len(inventory_rows) + len(covariate_rows)
        report = DataQualityReport(
            total, len(demands) + len(inventories) + len(covariates), tuple(errors)
        )
        if not report.passed:
            raise ValueError("data quality failed: " + "; ".join(report.errors))

        payload = json.dumps(
            {
                "demand": demand_rows,
                "inventory": inventory_rows,
                "covariates": covariate_rows,
                "snapshot": snapshot_time.isoformat(),
            },
            sort_keys=True,
            default=str,
        )
        version = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
        bindings = tuple(
            StoreNodeBinding(business_unit_id, store_id, node_id)
            for business_unit_id, store_id, node_id in sorted(
                {(item[0], item[1], item[2]) for item in demand_items}
            )
        )
        return RetailDataset(
            dataset_id="retail-minimal",
            version=version,
            snapshot_time=snapshot_time,
            demand_records=tuple(demands),
            inventory_records=tuple(inventories),
            quality=report,
            covariate_records=tuple(covariates),
            store_node_bindings=bindings,
        )
