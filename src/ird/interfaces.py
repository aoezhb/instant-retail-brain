from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Protocol

from .schema import BusinessState, Decision, DecisionConstraints, ModelOutput, RetailDataset


class DataProvider(Protocol):
    def load(self) -> list[Mapping[str, Any]]: ...


class DataHandler(Protocol):
    def build_dataset(
        self,
        demand_rows: list[Mapping[str, Any]],
        inventory_rows: list[Mapping[str, Any]],
        snapshot_time: datetime,
        covariate_rows: list[Mapping[str, Any]] | None = None,
    ) -> RetailDataset: ...


class RetailModel(Protocol):
    def fit(self, dataset: RetailDataset) -> None: ...
    def predict(self, dataset: RetailDataset, as_of: datetime) -> ModelOutput: ...
    def describe(self) -> Mapping[str, str]: ...


class DecisionPolicy(Protocol):
    def decide(
        self,
        model_output: ModelOutput,
        states: list[BusinessState],
        constraints: DecisionConstraints,
    ) -> list[Decision]: ...

    def explain(self, decision: Decision) -> str: ...
    def describe(self) -> Mapping[str, str]: ...
