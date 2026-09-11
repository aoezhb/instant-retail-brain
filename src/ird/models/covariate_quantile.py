from __future__ import annotations

from datetime import datetime
from math import sqrt
from statistics import NormalDist

from ..registry import ComponentAsset, register_model
from ..schema import ItemKey, ModelOutput, RetailDataset

FEATURE_NAMES = ("weekend", "promotion", "holiday", "temperature")


def _features(values: dict[str, float]) -> list[float]:
    return [
        1.0,
        values.get("weekend", 0.0),
        values.get("promotion", 0.0),
        values.get("holiday", 0.0),
        values.get("temperature", 0.0) / 20.0,
    ]


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    augmented = [row[:] + [value] for row, value in zip(matrix, vector)]
    size = len(vector)
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        if abs(scale) < 1e-12:
            raise ValueError("covariate matrix is singular")
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                current - factor * source
                for current, source in zip(augmented[row], augmented[column])
            ]
    return [row[-1] for row in augmented]


class CovariateQuantileDemandModel:
    """Ridge regression with normal residual quantiles."""

    def __init__(
        self,
        ridge: float = 0.1,
        quantiles: tuple[float, ...] = (0.1, 0.5, 0.9),
        horizon_days: int = 1,
    ) -> None:
        if ridge <= 0:
            raise ValueError("ridge must be positive")
        if horizon_days != 1 or any(not 0 < quantile < 1 for quantile in quantiles):
            raise ValueError("this model supports a one-day horizon and valid quantiles")
        self.ridge = ridge
        self.quantiles = tuple(sorted(set(quantiles)))
        self.horizon_days = horizon_days
        self._coefficients: dict[ItemKey, list[float]] = {}
        self._residual_std: dict[ItemKey, float] = {}
        self._fitted_version: str | None = None

    def fit(self, dataset: RetailDataset) -> None:
        coefficients: dict[ItemKey, list[float]] = {}
        residual_std: dict[ItemKey, float] = {}
        feature_count = len(FEATURE_NAMES) + 1
        for item in dataset.items:
            samples: list[tuple[list[float], float]] = []
            for demand in dataset.demand_for(item):
                if not demand.available:
                    continue
                covariates = dataset.covariates_for(
                    item, day=demand.day, available_at=demand.event_time
                )
                if covariates:
                    samples.append((_features(dict(covariates[-1].values)), demand.demand))
            if not samples:
                continue
            gram = [[0.0] * feature_count for _ in range(feature_count)]
            target = [0.0] * feature_count
            for row, demand in samples:
                for left in range(feature_count):
                    target[left] += row[left] * demand
                    for right in range(feature_count):
                        gram[left][right] += row[left] * row[right]
            for index in range(1, feature_count):
                gram[index][index] += self.ridge
            fitted = _solve(gram, target)
            residuals = [demand - sum(a * b for a, b in zip(row, fitted)) for row, demand in samples]
            variance = sum(value * value for value in residuals) / max(1, len(residuals) - 1)
            coefficients[item] = fitted
            residual_std[item] = sqrt(variance)
        if not coefficients:
            raise ValueError("covariate records are required for fitting")
        self._coefficients = coefficients
        self._residual_std = residual_std
        self._fitted_version = dataset.version

    def predict(self, dataset: RetailDataset, as_of: datetime) -> ModelOutput:
        if self._fitted_version is None:
            raise RuntimeError("fit must be called before predict")
        if dataset.version != self._fitted_version:
            raise ValueError("predict dataset must match the fitted snapshot version")
        dataset.assert_available_at(as_of)
        forecasts: dict[ItemKey, float] = {}
        intervals: dict[ItemKey, dict[float, float]] = {}
        for item, coefficients in self._coefficients.items():
            candidates = dataset.covariates_for(item, day=as_of.date(), available_at=as_of)
            values = dict(candidates[-1].values) if candidates else {}
            point = max(0.0, sum(a * b for a, b in zip(_features(values), coefficients)))
            forecasts[item] = point
            deviation = self._residual_std[item]
            intervals[item] = {
                quantile: max(0.0, point + NormalDist().inv_cdf(quantile) * deviation)
                for quantile in self.quantiles
            }
        return ModelOutput(
            "covariate_quantile", "0.1.0", dataset.version, as_of, "store",
            forecasts, self.horizon_days, intervals,
        )

    def describe(self) -> dict[str, str]:
        return {
            "name": "covariate_quantile",
            "version": "0.1.0",
            "task": "probabilistic_demand_forecast",
            "features": ",".join(FEATURE_NAMES),
            "quantiles": ",".join(str(value) for value in self.quantiles),
            "ridge": str(self.ridge),
            "input_snapshot_version": self._fitted_version or "not-fitted",
            "limitation": "Normal residual approximation on a small linear feature set.",
        }


register_model(
    "covariate_quantile",
    CovariateQuantileDemandModel,
    ComponentAsset(
        "model", "covariate_quantile", "0.1.0", "RetailDataset+CovariateRecord",
        "ModelOutput(point+quantiles)", ("ridge", "quantiles", "horizon_days"),
        "Compact probabilistic baseline; customer data requires calibration and feature review.",
    ),
)
