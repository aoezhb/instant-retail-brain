from __future__ import annotations

from datetime import datetime
from typing import Any

from ..registry import ComponentAsset, register_model
from ..schema import ItemKey, ModelOutput, RetailDataset


class LightGBMDemandModel:
    """Global gradient-boosted demand model with point and quantile outputs."""

    def __init__(
        self,
        n_estimators: int = 100,
        learning_rate: float = 0.05,
        num_leaves: int = 15,
        quantiles: tuple[float, ...] = (0.1, 0.5, 0.9),
        horizon_days: int = 1,
        random_state: int = 42,
    ) -> None:
        if n_estimators < 1 or learning_rate <= 0 or num_leaves < 2:
            raise ValueError("LightGBM training parameters must be positive")
        if horizon_days != 1 or any(not 0 < quantile < 1 for quantile in quantiles):
            raise ValueError("this model supports a one-day horizon and valid quantiles")
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.num_leaves = num_leaves
        self.quantiles = tuple(sorted(set(quantiles)))
        self.horizon_days = horizon_days
        self.random_state = random_state
        self._item_indices: dict[ItemKey, int] = {}
        self._point_model: Any | None = None
        self._quantile_models: dict[float, Any] = {}
        self._fitted_version: str | None = None

    @staticmethod
    def _load_regressor() -> Any:
        try:
            from lightgbm import LGBMRegressor
        except ImportError as exc:
            raise RuntimeError(
                'LightGBM support is optional; install it with pip install -e ".[lightgbm]"'
            ) from exc
        return LGBMRegressor

    @staticmethod
    def _feature_row(
        item_index: int,
        day_of_week: int,
        covariates: dict[str, float],
        history: list[float],
    ) -> list[float]:
        lag_one = history[-1] if history else 0.0
        recent = history[-7:]
        rolling_mean = sum(recent) / len(recent) if recent else 0.0
        return [
            float(item_index),
            day_of_week / 6.0,
            covariates.get("weekend", 0.0),
            covariates.get("promotion", 0.0),
            covariates.get("holiday", 0.0),
            covariates.get("temperature", 0.0) / 20.0,
            lag_one,
            rolling_mean,
        ]

    def _model_parameters(self, objective: str, **extra: Any) -> dict[str, Any]:
        return {
            "objective": objective,
            "n_estimators": self.n_estimators,
            "learning_rate": self.learning_rate,
            "num_leaves": self.num_leaves,
            "min_child_samples": 1,
            "random_state": self.random_state,
            "n_jobs": 1,
            "verbosity": -1,
            "deterministic": True,
            "force_col_wise": True,
            **extra,
        }

    def fit(self, dataset: RetailDataset) -> None:
        regressor = self._load_regressor()
        self._item_indices = {item: index for index, item in enumerate(dataset.items)}
        features: list[list[float]] = []
        targets: list[float] = []
        for item, item_index in self._item_indices.items():
            history: list[float] = []
            for demand in dataset.demand_for(item):
                if not demand.available:
                    continue
                candidates = dataset.covariates_for(
                    item, day=demand.day, available_at=demand.event_time
                )
                values = dict(candidates[-1].values) if candidates else {}
                features.append(
                    self._feature_row(item_index, demand.day.weekday(), values, history)
                )
                targets.append(demand.demand)
                history.append(demand.demand)
        if not targets:
            raise ValueError("cannot fit LightGBM on an empty dataset")

        point_model = regressor(**self._model_parameters("regression_l1"))
        point_model.fit(features, targets, categorical_feature=[0])
        quantile_models: dict[float, Any] = {}
        for quantile in self.quantiles:
            model = regressor(**self._model_parameters("quantile", alpha=quantile))
            model.fit(features, targets, categorical_feature=[0])
            quantile_models[quantile] = model
        self._point_model = point_model
        self._quantile_models = quantile_models
        self._fitted_version = dataset.version

    def predict(self, dataset: RetailDataset, as_of: datetime) -> ModelOutput:
        if self._point_model is None or self._fitted_version is None:
            raise RuntimeError("fit must be called before predict")
        if dataset.version != self._fitted_version:
            raise ValueError("predict dataset must match the fitted snapshot version")
        dataset.assert_available_at(as_of)

        items = sorted(self._item_indices, key=self._item_indices.get)
        features: list[list[float]] = []
        for item in items:
            history = [
                record.demand for record in dataset.demand_for(item) if record.available
            ]
            candidates = dataset.covariates_for(item, day=as_of.date(), available_at=as_of)
            values = dict(candidates[-1].values) if candidates else {}
            features.append(
                self._feature_row(
                    self._item_indices[item], as_of.date().weekday(), values, history
                )
            )

        point_values = self._point_model.predict(features)
        forecasts = {
            item: max(0.0, float(value)) for item, value in zip(items, point_values)
        }
        raw_quantiles = {
            quantile: model.predict(features)
            for quantile, model in self._quantile_models.items()
        }
        intervals: dict[ItemKey, dict[float, float]] = {}
        for index, item in enumerate(items):
            previous = 0.0
            ordered: dict[float, float] = {}
            for quantile in self.quantiles:
                value = max(previous, max(0.0, float(raw_quantiles[quantile][index])))
                ordered[quantile] = value
                previous = value
            intervals[item] = ordered
        return ModelOutput(
            "lightgbm", "0.1.0", dataset.version, as_of, "store", forecasts,
            self.horizon_days, intervals,
        )

    def describe(self) -> dict[str, str]:
        return {
            "name": "lightgbm",
            "version": "0.1.0",
            "task": "probabilistic_demand_forecast",
            "n_estimators": str(self.n_estimators),
            "learning_rate": str(self.learning_rate),
            "num_leaves": str(self.num_leaves),
            "quantiles": ",".join(str(value) for value in self.quantiles),
            "features": "item,calendar,covariates,lag_1,rolling_mean_7",
            "input_snapshot_version": self._fitted_version or "not-fitted",
            "limitation": "Small synthetic samples do not demonstrate production accuracy.",
        }


register_model(
    "lightgbm",
    LightGBMDemandModel,
    ComponentAsset(
        "model", "lightgbm", "0.1.0", "RetailDataset+CovariateRecord",
        "ModelOutput(point+quantiles)",
        ("n_estimators", "learning_rate", "num_leaves", "quantiles", "horizon_days"),
        "Optional LightGBM dependency; customer data needs tuning and calibration.",
    ),
)
