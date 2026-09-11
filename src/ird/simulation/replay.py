from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from collections import defaultdict

from ..schema import Decision, ItemKey, RetailDataset


@dataclass(frozen=True)
class ItemReplayResult:
    item: ItemKey
    stockout_events: int
    ending_inventory: float
    ordered_units: float
    served_units: float
    demanded_units: float


@dataclass(frozen=True)
class ReplayResult:
    items: tuple[ItemReplayResult, ...]

    @property
    def stockout_events(self) -> int:
        return sum(item.stockout_events for item in self.items)

    @property
    def ordered_units(self) -> float:
        return round(sum(item.ordered_units for item in self.items), 2)

    @property
    def served_units(self) -> float:
        return round(sum(item.served_units for item in self.items), 2)

    @property
    def demanded_units(self) -> float:
        return round(sum(item.demanded_units for item in self.items), 2)

    @property
    def ending_inventory(self) -> float:
        return round(sum(item.ending_inventory for item in self.items), 2)


def replay_inventory(
    dataset: RetailDataset,
    decisions: list[Decision],
    start_day: date | None = None,
    initial_inventory_dataset: RetailDataset | None = None,
) -> ReplayResult:
    """Replay immediate order receipt once, then consume daily potential demand."""
    decisions_by_item: dict[ItemKey, float] = defaultdict(float)
    for decision in decisions:
        if decision.decision_type == "replenishment":
            decisions_by_item[
                (
                    decision.business_unit_id,
                    decision.store_id,
                    decision.node_id,
                    decision.sku_id,
                )
            ] += decision.quantity
    inventory_dataset = initial_inventory_dataset or dataset
    if start_day is None:
        start_day = inventory_dataset.snapshot_time.date()
    item_results: list[ItemReplayResult] = []
    for item in dataset.items:
        inventory_record = inventory_dataset.inventory_for(item)
        ordered = decisions_by_item.get(item, 0.0)
        inventory = inventory_record.available_inventory + ordered
        served = 0.0
        demanded = 0.0
        stockout_events = 0
        records = dataset.demand_for(item)
        records = tuple(record for record in records if record.day >= start_day)
        for record in records:
            demanded += record.demand
            served_today = min(inventory, record.demand) if record.available else 0.0
            served += served_today
            inventory -= served_today
            if served_today < record.demand:
                stockout_events += 1
        item_results.append(
            ItemReplayResult(
                item, stockout_events, round(inventory, 2), round(ordered, 2),
                round(served, 2), round(demanded, 2),
            )
        )
    return ReplayResult(tuple(item_results))
