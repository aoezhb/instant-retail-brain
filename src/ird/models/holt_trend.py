from __future__ import annotations

from datetime import datetime

from ..registry import ComponentAsset, register_model
from ..schema import ItemKey, ModelOutput, RetailDataset


class HoltTrendDemandModel:
    """Double exponential smoothing baseline for demand with local trend."""

    def __init__(self, alpha: float = 0.6, beta: float = 0.2, horizon_days: int = 1) -> None:
        if not 0 < alpha <= 1 or not 0 <= beta <= 1:
            raise ValueError("alpha and beta must be between 0 and 1")
        if horizon_days < 1:
            raise ValueError("horizon_days must be positive")
        self.alpha = alpha
        self.beta = beta
        self.horizon_days = horizon_days
        self._state: dict[ItemKey, tuple[float, float]] = {}
        self._fitted_version: str | None = None

    def fit(self, dataset: RetailDataset) -> None:
        state: dict[ItemKey, tuple[float, float]] = {}
        for item in dataset.items:
            values = [record.demand for record in dataset.demand_for(item) if record.available]
            if not values:
                continue
            level = values[0]
            trend = values[1] - values[0] if len(values) > 1 else 0.0
            for value in values[1:]:
                previous_level = level
                level = self.alpha * value + (1 - self.alpha) * (level + trend)
                trend = self.beta * (level - previous_level) + (1 - self.beta) * trend
            state[item] = (level, trend)
        if not state:
            raise ValueError("cannot fit on an empty dataset")
        self._state = state
        self._fitted_version = dataset.version

    def predict(self, dataset: RetailDataset, as_of: datetime) -> ModelOutput:
        if self._fitted_version is None:
            raise RuntimeError("fit must be called before predict")
        if dataset.version != self._fitted_version:
            raise ValueError("predict dataset must match the fitted snapshot version")
        dataset.assert_available_at(as_of)
        forecasts = {}
        for item, (level, trend) in self._state.items():
            daily_values = [
                max(0.0, level + trend * step)
                for step in range(1, self.horizon_days + 1)
            ]
            forecasts[item] = sum(daily_values) / len(daily_values)
        return ModelOutput(
            "holt_trend", "0.1.0", dataset.version, as_of, "store", forecasts,
            self.horizon_days,
        )

    def describe(self) -> dict[str, str]:
        return {
            "name": "holt_trend",
            "version": "0.1.0",
            "task": "demand_forecast",
            "alpha": str(self.alpha),
            "beta": str(self.beta),
            "horizon_days": str(self.horizon_days),
            "input_snapshot_version": self._fitted_version or "not-fitted",
            "limitation": "Local trend baseline without seasonality or prediction intervals.",
        }


register_model(
    "holt_trend",
    HoltTrendDemandModel,
    ComponentAsset(
        "model", "holt_trend", "0.1.0", "RetailDataset", "ModelOutput",
        ("alpha", "beta", "horizon_days"),
        "Double exponential smoothing; not suitable for abrupt structural changes.",
    ),
)
