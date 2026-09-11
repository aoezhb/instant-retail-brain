from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ComponentAsset:
    category: str
    name: str
    version: str
    input_schema: str
    output_schema: str
    parameters: tuple[str, ...]
    limitations: str


_MODELS: dict[str, Callable[..., Any]] = {}
_POLICIES: dict[str, Callable[..., Any]] = {}
_ASSETS: dict[tuple[str, str], ComponentAsset] = {}


def _require_methods(factory: Callable[..., Any], methods: tuple[str, ...], category: str) -> None:
    missing = [method for method in methods if not callable(getattr(factory, method, None))]
    if missing:
        raise TypeError(f"{category} component is missing methods: {','.join(missing)}")


def register_asset(asset: ComponentAsset) -> None:
    key = (asset.category, asset.name)
    if key in _ASSETS:
        raise ValueError(f"asset already registered: {asset.category}/{asset.name}")
    _ASSETS[key] = asset


def register_model(name: str, factory: Callable[..., Any], asset: ComponentAsset) -> None:
    if name in _MODELS:
        raise ValueError(f"model already registered: {name}")
    if asset.category != "model" or asset.name != name:
        raise ValueError("model asset metadata does not match registry name")
    _require_methods(factory, ("fit", "predict", "describe"), "model")
    register_asset(asset)
    _MODELS[name] = factory


def register_policy(name: str, factory: Callable[..., Any], asset: ComponentAsset) -> None:
    if name in _POLICIES:
        raise ValueError(f"policy already registered: {name}")
    if asset.category != "policy" or asset.name != name:
        raise ValueError("policy asset metadata does not match registry name")
    _require_methods(factory, ("decide", "explain", "describe"), "policy")
    register_asset(asset)
    _POLICIES[name] = factory


def get_model(name: str, **kwargs: Any) -> Any:
    try:
        factory = _MODELS[name]
    except KeyError as exc:
        raise KeyError(f"unknown model: {name}") from exc
    return factory(**kwargs)


def get_policy(name: str, **kwargs: Any) -> Any:
    try:
        factory = _POLICIES[name]
    except KeyError as exc:
        raise KeyError(f"unknown policy: {name}") from exc
    return factory(**kwargs)


def list_components() -> dict[str, tuple[str, ...]]:
    return {"models": tuple(sorted(_MODELS)), "policies": tuple(sorted(_POLICIES))}


def list_assets(category: str | None = None) -> tuple[ComponentAsset, ...]:
    assets = (asset for asset in _ASSETS.values() if category is None or asset.category == category)
    return tuple(sorted(assets, key=lambda asset: (asset.category, asset.name)))


register_asset(
    ComponentAsset(
        "dataset", "demand_inventory_covariates", "0.1.0",
        "DemandRecord+InventoryRecord+CovariateRecord", "RetailDataset",
        ("snapshot_time",), "Synthetic and file-based demonstration data only.",
    )
)
register_asset(
    ComponentAsset(
        "scenario", "baseline_replenishment", "0.1.0", "RetailDataset",
        "ReplayResult", ("initial_inventory",),
        "Descriptive asset; this demo does not load scenario plugins at runtime.",
    )
)
