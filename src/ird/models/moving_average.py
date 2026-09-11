from __future__ import annotations

from datetime import datetime

from ..registry import ComponentAsset, register_model
from ..schema import ModelOutput, RetailDataset


class MovingAverageDemandModel:
    def __init__(self, window: int = 7, horizon_days: int = 1) -> None:
        if window < 1 or horizon_days < 1:
            raise ValueError("window and horizon_days must be positive")
        self.window = window
        self.horizon_days = horizon_days
        self._fitted_version: str | None = None

    def fit(self, dataset: RetailDataset) -> None:
        if not dataset.demand_records:
            raise ValueError("cannot fit on an empty dataset")
        self._fitted_version = dataset.version

    def predict(self, dataset: RetailDataset, as_of: datetime) -> ModelOutput:
        if self._fitted_version is None:
            raise RuntimeError("fit must be called before predict")
        if dataset.version != self._fitted_version:
            raise ValueError("predict dataset must match the fitted snapshot version")
        dataset.assert_available_at(as_of)
        forecasts = {}
        for item in dataset.items:
            usable = [record.demand for record in dataset.demand_for(item) if record.available]
            window = usable[-self.window :]
            forecasts[item] = sum(window) / len(window) if window else 0.0
        return ModelOutput(
            "moving_average", "0.1.0", dataset.version, as_of, "store", forecasts, self.horizon_days
        )

    def describe(self) -> dict[str, str]:
        return {
            "name": "moving_average",
            "version": "0.1.0",
            "task": "demand_forecast",
            "window": str(self.window),
            "horizon_days": str(self.horizon_days),
            "input_snapshot_version": self._fitted_version or "not-fitted",
            "limitation": "Ignores unavailable observations and external covariates.",
        }


register_model(
    "moving_average",
    MovingAverageDemandModel,
    ComponentAsset(
        "model", "moving_average", "0.1.0", "RetailDataset", "ModelOutput",
        ("window", "horizon_days"), "Point forecast baseline without external covariates.",
    ),
)
