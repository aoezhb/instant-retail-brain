from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from math import isfinite
from typing import Any, Mapping, TypeAlias

ItemKey: TypeAlias = tuple[str, str, str, str]


def _require_id(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _require_nonnegative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


@dataclass(frozen=True)
class BusinessUnit:
    business_unit_id: str
    name: str

    def __post_init__(self) -> None:
        _require_id("business_unit_id", self.business_unit_id)


@dataclass(frozen=True)
class Store:
    business_unit_id: str
    store_id: str
    name: str

    def __post_init__(self) -> None:
        _require_id("business_unit_id", self.business_unit_id)
        _require_id("store_id", self.store_id)


@dataclass(frozen=True)
class FulfillmentNode:
    business_unit_id: str
    node_id: str
    name: str

    def __post_init__(self) -> None:
        _require_id("business_unit_id", self.business_unit_id)
        _require_id("node_id", self.node_id)


@dataclass(frozen=True)
class StoreNodeBinding:
    business_unit_id: str
    store_id: str
    node_id: str
    role: str = "serves"

    def __post_init__(self) -> None:
        _require_id("business_unit_id", self.business_unit_id)
        _require_id("store_id", self.store_id)
        _require_id("node_id", self.node_id)
        _require_id("role", self.role)


@dataclass(frozen=True)
class DemandRecord:
    business_unit_id: str
    store_id: str
    node_id: str
    sku_id: str
    day: date
    demand: float
    available: bool
    event_time: datetime
    available_time: datetime

    def __post_init__(self) -> None:
        for name in ("business_unit_id", "store_id", "node_id", "sku_id"):
            _require_id(name, getattr(self, name))
        if not isfinite(self.demand) or self.demand < 0:
            raise ValueError("demand must be a finite nonnegative number")
        if not isinstance(self.available, bool):
            raise ValueError("available must be boolean")
        _require_aware("event_time", self.event_time)
        _require_aware("available_time", self.available_time)
        if self.available_time < self.event_time:
            raise ValueError("available_time cannot be before demand event_time")

    @property
    def item_key(self) -> ItemKey:
        return (self.business_unit_id, self.store_id, self.node_id, self.sku_id)


@dataclass(frozen=True)
class CovariateRecord:
    business_unit_id: str
    store_id: str
    node_id: str
    sku_id: str
    day: date
    values: Mapping[str, float]
    event_time: datetime
    available_time: datetime

    def __post_init__(self) -> None:
        for name in ("business_unit_id", "store_id", "node_id", "sku_id"):
            _require_id(name, getattr(self, name))
        if not self.values or any(not isfinite(value) for value in self.values.values()):
            raise ValueError("covariates must contain finite numeric values")
        _require_aware("event_time", self.event_time)
        _require_aware("available_time", self.available_time)

    @property
    def item_key(self) -> ItemKey:
        return (self.business_unit_id, self.store_id, self.node_id, self.sku_id)


@dataclass(frozen=True)
class InventoryRecord:
    business_unit_id: str
    store_id: str
    node_id: str
    sku_id: str
    available_inventory: float
    on_order: float
    reserved_inventory: float
    backorders: float
    unit_cost: float
    lead_time_days: int
    review_period_days: int
    snapshot_time: datetime
    selling_price: float = 0.0
    regular_price: float = 0.0
    days_to_expiry: int | None = None

    def __post_init__(self) -> None:
        for name in ("business_unit_id", "store_id", "node_id", "sku_id"):
            _require_id(name, getattr(self, name))
        numeric = (
            self.available_inventory,
            self.on_order,
            self.reserved_inventory,
            self.backorders,
            self.unit_cost,
            self.selling_price,
            self.regular_price,
        )
        if any(not isfinite(value) or value < 0 for value in numeric):
            raise ValueError("inventory quantities, costs, and prices must be finite and nonnegative")
        _require_nonnegative_int("lead_time_days", self.lead_time_days)
        _require_nonnegative_int("review_period_days", self.review_period_days)
        if self.days_to_expiry is not None:
            _require_nonnegative_int("days_to_expiry", self.days_to_expiry)
        _require_aware("snapshot_time", self.snapshot_time)

    @property
    def item_key(self) -> ItemKey:
        return (self.business_unit_id, self.store_id, self.node_id, self.sku_id)

    @property
    def inventory_position(self) -> float:
        return self.available_inventory + self.on_order - self.reserved_inventory - self.backorders


@dataclass(frozen=True)
class DataQualityReport:
    total_rows: int
    valid_rows: int
    errors: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.errors and self.total_rows == self.valid_rows


@dataclass(frozen=True)
class RetailDataset:
    dataset_id: str
    version: str
    snapshot_time: datetime
    demand_records: tuple[DemandRecord, ...]
    inventory_records: tuple[InventoryRecord, ...]
    quality: DataQualityReport
    covariate_records: tuple[CovariateRecord, ...] = ()
    store_node_bindings: tuple[StoreNodeBinding, ...] = ()

    def __post_init__(self) -> None:
        _require_id("dataset_id", self.dataset_id)
        _require_id("version", self.version)
        _require_aware("snapshot_time", self.snapshot_time)

    @property
    def items(self) -> tuple[ItemKey, ...]:
        return tuple(sorted({record.item_key for record in self.demand_records}))

    def demand_for(self, item: ItemKey) -> tuple[DemandRecord, ...]:
        return tuple(sorted((r for r in self.demand_records if r.item_key == item), key=lambda r: r.day))

    def inventory_for(self, item: ItemKey) -> InventoryRecord:
        matches = [record for record in self.inventory_records if record.item_key == item]
        if len(matches) != 1:
            raise KeyError(f"expected one inventory record for {item}, found {len(matches)}")
        return matches[0]

    def covariates_for(
        self,
        item: ItemKey,
        day: date | None = None,
        available_at: datetime | None = None,
    ) -> tuple[CovariateRecord, ...]:
        records = (record for record in self.covariate_records if record.item_key == item)
        if day is not None:
            records = (record for record in records if record.day == day)
        if available_at is not None:
            records = (record for record in records if record.available_time <= available_at)
        return tuple(sorted(records, key=lambda record: (record.day, record.available_time)))

    def assert_available_at(self, as_of: datetime) -> None:
        _require_aware("as_of", as_of)
        if self.snapshot_time > as_of:
            raise ValueError("dataset snapshot is after the prediction time")


@dataclass(frozen=True)
class ModelOutput:
    model_name: str
    model_version: str
    input_snapshot_version: str
    generated_at: datetime
    forecast_scope: str
    forecasts: Mapping[ItemKey, float]
    horizon_days: int
    quantiles: Mapping[ItemKey, Mapping[float, float]] = field(default_factory=dict)
    forecast_semantics: str = "daily_rate"

    def __post_init__(self) -> None:
        for name in ("model_name", "model_version", "input_snapshot_version", "forecast_scope"):
            _require_id(name, getattr(self, name))
        _require_aware("generated_at", self.generated_at)
        if self.horizon_days < 1:
            raise ValueError("horizon_days must be positive")
        if self.forecast_semantics != "daily_rate":
            raise ValueError("forecast_semantics must be daily_rate")
        if any(not isfinite(value) or value < 0 for value in self.forecasts.values()):
            raise ValueError("forecasts must be finite and nonnegative")
        for distribution in self.quantiles.values():
            if any(not 0 < quantile < 1 for quantile in distribution):
                raise ValueError("forecast quantiles must be between 0 and 1")
            if any(not isfinite(value) or value < 0 for value in distribution.values()):
                raise ValueError("forecast quantile values must be finite and nonnegative")


@dataclass(frozen=True)
class BusinessState:
    business_unit_id: str
    store_id: str
    node_id: str
    sku_id: str
    available_inventory: float
    on_order: float
    reserved_inventory: float
    backorders: float
    unit_cost: float
    lead_time_days: int
    review_period_days: int
    selling_price: float = 0.0
    regular_price: float = 0.0
    days_to_expiry: int | None = None
    snapshot_time: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("business_unit_id", "store_id", "node_id", "sku_id"):
            _require_id(name, getattr(self, name))
        numeric = (
            self.available_inventory,
            self.on_order,
            self.reserved_inventory,
            self.backorders,
            self.unit_cost,
            self.selling_price,
            self.regular_price,
        )
        if any(not isfinite(value) or value < 0 for value in numeric):
            raise ValueError("business state quantities, costs, and prices must be finite and nonnegative")
        _require_nonnegative_int("lead_time_days", self.lead_time_days)
        _require_nonnegative_int("review_period_days", self.review_period_days)
        if self.days_to_expiry is not None:
            _require_nonnegative_int("days_to_expiry", self.days_to_expiry)
        if self.snapshot_time is not None:
            _require_aware("snapshot_time", self.snapshot_time)

    @property
    def item_key(self) -> ItemKey:
        return (self.business_unit_id, self.store_id, self.node_id, self.sku_id)

    @property
    def inventory_position(self) -> float:
        return self.available_inventory + self.on_order - self.reserved_inventory - self.backorders


@dataclass(frozen=True)
class DecisionConstraints:
    max_units: float = 10_000
    max_spend: float = 100_000
    min_order_qty: float = 1
    service_level: float = 0.90
    approval_spend_threshold: float = 5_000
    allow_external_write: bool = False

    def __post_init__(self) -> None:
        numeric = (
            self.max_units,
            self.max_spend,
            self.min_order_qty,
            self.service_level,
            self.approval_spend_threshold,
        )
        if any(not isfinite(value) for value in numeric):
            raise ValueError("decision constraints must be finite")
        if self.max_units <= 0 or self.max_spend < 0 or self.min_order_qty <= 0:
            raise ValueError("quantity and spend constraints must be positive")
        if not 0 < self.service_level < 1:
            raise ValueError("service_level must be between 0 and 1")
        if self.approval_spend_threshold < 0:
            raise ValueError("approval_spend_threshold cannot be negative")
        if not isinstance(self.allow_external_write, bool):
            raise ValueError("allow_external_write must be boolean")


@dataclass(frozen=True)
class Decision:
    decision_id: str
    decision_type: str
    business_unit_id: str
    store_id: str
    node_id: str
    fulfillment_node_id: str | None
    sku_id: str
    recommended_action: str
    quantity: float
    estimated_spend: float
    reason_codes: tuple[str, ...]
    expected_effect: Mapping[str, float]
    risk_summary: str
    constraints_applied: tuple[str, ...]
    approval_required: bool
    expires_at: datetime
    action_context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "decision_id",
            "decision_type",
            "business_unit_id",
            "store_id",
            "node_id",
            "sku_id",
            "recommended_action",
        ):
            _require_id(name, getattr(self, name))
        if not isfinite(self.quantity) or not isfinite(self.estimated_spend):
            raise ValueError("decision quantity and spend must be finite")
        if self.fulfillment_node_id is not None:
            _require_id("fulfillment_node_id", self.fulfillment_node_id)
        if not isinstance(self.approval_required, bool):
            raise ValueError("approval_required must be boolean")
        _require_aware("expires_at", self.expires_at)


@dataclass(frozen=True)
class ExecutionReceipt:
    decision_id: str
    status: str
    reason: str
    executed_at: datetime

    def __post_init__(self) -> None:
        _require_id("decision_id", self.decision_id)
        _require_id("reason", self.reason)
        if self.status not in {"accepted", "rejected"}:
            raise ValueError("receipt status must be accepted or rejected")
        _require_aware("executed_at", self.executed_at)


@dataclass(frozen=True)
class ApprovalRecord:
    decision_id: str
    status: str
    decided_by: str
    decided_at: datetime
    comment: str = ""

    def __post_init__(self) -> None:
        _require_id("decision_id", self.decision_id)
        _require_id("decided_by", self.decided_by)
        if self.status not in {"approved", "rejected"}:
            raise ValueError("approval status must be approved or rejected")
        _require_aware("decided_at", self.decided_at)
