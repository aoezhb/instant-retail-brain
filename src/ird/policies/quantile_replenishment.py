from __future__ import annotations

from datetime import timedelta
from math import sqrt
from statistics import NormalDist
from uuid import NAMESPACE_URL, uuid5

from ..registry import ComponentAsset, register_policy
from ..schema import BusinessState, Decision, DecisionConstraints, ModelOutput


class QuantileReplenishmentPolicy:
    """Order-up-to policy driven by the forecast quantile nearest the service target."""

    def decide(
        self,
        model_output: ModelOutput,
        states: list[BusinessState],
        constraints: DecisionConstraints,
    ) -> list[Decision]:
        decisions: list[Decision] = []
        if model_output.forecast_semantics != "daily_rate":
            raise ValueError("quantile replenishment requires daily-rate forecasts")
        for state in states:
            distribution = model_output.quantiles.get(state.item_key, {})
            eligible = [value for value in distribution if value >= constraints.service_level]
            selected_quantile = min(eligible) if eligible else (max(distribution) if distribution else None)
            daily_quantile = (
                distribution[selected_quantile]
                if selected_quantile is not None
                else model_output.forecasts.get(state.item_key, 0.0)
            )
            daily_point = model_output.forecasts.get(state.item_key, daily_quantile)
            protection_days = state.lead_time_days + state.review_period_days
            target_inventory = daily_point * protection_days
            if selected_quantile is not None and selected_quantile != 0.5:
                z_score = NormalDist().inv_cdf(selected_quantile)
                median = distribution.get(0.5, daily_point)
                daily_std = max(0.0, (daily_quantile - median) / z_score)
                target_inventory = (
                    median * protection_days
                    + z_score * daily_std * sqrt(protection_days)
                )
            target_inventory = max(0.0, target_inventory)
            quantity = min(max(0.0, target_inventory - state.inventory_position), constraints.max_units)
            if 0 < quantity < constraints.min_order_qty:
                quantity = constraints.min_order_qty
            if state.unit_cost > 0:
                quantity = min(quantity, constraints.max_spend / state.unit_cost)
            quantity = round(quantity, 2)
            if quantity <= 0:
                continue
            spend = round(quantity * state.unit_cost, 2)
            identity = "|".join(
                (
                    "quantile_replenishment", model_output.input_snapshot_version,
                    *state.item_key, str(quantity),
                )
            )
            decisions.append(
                Decision(
                    decision_id=str(uuid5(NAMESPACE_URL, identity)),
                    decision_type="replenishment",
                    business_unit_id=state.business_unit_id,
                    store_id=state.store_id,
                    node_id=state.node_id,
                    fulfillment_node_id=None,
                    sku_id=state.sku_id,
                    recommended_action="order",
                    quantity=quantity,
                    estimated_spend=spend,
                    reason_codes=("probabilistic_service_level", "order_up_to_target"),
                    expected_effect={"target_inventory": round(target_inventory, 2)},
                    risk_summary="Quantile quality must be calibrated before production use.",
                    constraints_applied=("service_level", "max_units", "max_spend", "min_order_qty"),
                    approval_required=spend >= constraints.approval_spend_threshold,
                    expires_at=model_output.generated_at + timedelta(days=1),
                    action_context={
                        "forecast_daily": round(daily_point, 4),
                        "selected_quantile": selected_quantile or 0.0,
                        "cumulative_demand_quantile": round(target_inventory, 4),
                        "inventory_position": round(state.inventory_position, 2),
                    },
                )
            )
        return decisions

    def explain(self, decision: Decision) -> str:
        quantile = decision.action_context["selected_quantile"]
        return f"Order {decision.quantity:g} units using demand quantile P{quantile * 100:g}."

    def describe(self) -> dict[str, str]:
        return {
            "name": "quantile_replenishment",
            "version": "0.1.0",
            "task": "replenishment",
            "limitation": "Requires calibrated probabilistic forecasts.",
        }


register_policy(
    "quantile_replenishment",
    QuantileReplenishmentPolicy,
    ComponentAsset(
        "policy", "quantile_replenishment", "0.1.0",
        "ModelOutput(point+quantiles)+BusinessState+DecisionConstraints", "Decision",
        (), "Uses the nearest available quantile at or above the requested service level.",
    ),
)
