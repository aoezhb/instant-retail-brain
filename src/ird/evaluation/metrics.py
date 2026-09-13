from __future__ import annotations

from collections.abc import Iterable
from math import sqrt
from typing import Mapping, Sequence

from ..schema import Decision
from ..simulation.replay import ReplayResult


def _pairs(actual: Sequence[float], predicted: Sequence[float]) -> list[tuple[float, float]]:
    if len(actual) != len(predicted):
        raise ValueError("actual and predicted sequences must have the same length")
    return list(zip(actual, predicted))


def mae(actual: Sequence[float], predicted: Sequence[float]) -> float:
    pairs = _pairs(actual, predicted)
    return round(sum(abs(a - p) for a, p in pairs) / len(pairs), 4) if pairs else 0.0


def rmse(actual: Sequence[float], predicted: Sequence[float]) -> float:
    pairs = _pairs(actual, predicted)
    return round(sqrt(sum((a - p) ** 2 for a, p in pairs) / len(pairs)), 4) if pairs else 0.0


def wape(actual: Sequence[float], predicted: Sequence[float]) -> float:
    pairs = _pairs(actual, predicted)
    denominator = sum(abs(a) for a, _ in pairs)
    return round(sum(abs(a - p) for a, p in pairs) / denominator, 4) if denominator else 0.0


def quantile_coverage(actual: Sequence[float], quantile: Sequence[float]) -> float:
    pairs = _pairs(actual, quantile)
    return round(sum(a <= q for a, q in pairs) / len(pairs), 4) if pairs else 0.0


def summarize_forecast_metrics(
    actual: Sequence[float], predicted: Sequence[float],
    p50: Sequence[float] | None = None, p90: Sequence[float] | None = None,
) -> dict[str, float]:
    metrics = {"mae": mae(actual, predicted), "rmse": rmse(actual, predicted), "wape": wape(actual, predicted)}
    if p50 is not None:
        metrics["p50_coverage"] = quantile_coverage(actual, p50)
    if p90 is not None:
        metrics["p90_coverage"] = quantile_coverage(actual, p90)
    return metrics


def evaluate_replay(
    result: ReplayResult,
    decisions: Iterable[Decision] = (),
) -> dict[str, float]:
    fill_rate = result.served_units / result.demanded_units if result.demanded_units else 1.0
    committed_spend = sum(decision.estimated_spend for decision in decisions)
    return {
        "stockout_events": float(result.stockout_events),
        "fill_rate": round(fill_rate, 4),
        "stockout_rate": round(1.0 - fill_rate, 4),
        "ordered_units": result.ordered_units,
        "ending_inventory": result.ending_inventory,
        "committed_spend": round(committed_spend, 2),
        "order_amount": round(committed_spend, 2),
    }


def evaluate_operating_metrics(
    result: ReplayResult, decisions: Iterable[Decision] = (),
    rejected_decisions: int = 0, approval_required: int = 0,
    total_decisions: int | None = None,
) -> Mapping[str, float]:
    decisions = list(decisions)
    total = total_decisions if total_decisions is not None else len(decisions) + rejected_decisions
    avg_inventory = result.average_inventory
    return {
        "stockout_rate": round(1.0 - (result.served_units / result.demanded_units if result.demanded_units else 1.0), 4),
        "inventory_turnover": round(result.served_units / avg_inventory, 4) if avg_inventory else 0.0,
        "average_inventory": round(avg_inventory, 2),
        "order_amount": round(sum(d.estimated_spend for d in decisions), 2),
        "executor_rejection_rate": round(rejected_decisions / total, 4) if total else 0.0,
        "approval_required_rate": round(approval_required / total, 4) if total else 0.0,
    }
