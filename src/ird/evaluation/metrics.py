from __future__ import annotations

from collections.abc import Iterable

from ..schema import Decision
from ..simulation.replay import ReplayResult


def evaluate_replay(
    result: ReplayResult,
    decisions: Iterable[Decision] = (),
) -> dict[str, float]:
    fill_rate = result.served_units / result.demanded_units if result.demanded_units else 1.0
    committed_spend = sum(decision.estimated_spend for decision in decisions)
    return {
        "stockout_events": float(result.stockout_events),
        "fill_rate": round(fill_rate, 4),
        "ordered_units": result.ordered_units,
        "ending_inventory": result.ending_inventory,
        "committed_spend": round(committed_spend, 2),
    }
