from __future__ import annotations

from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from ..registry import ComponentAsset, register_policy
from ..schema import BusinessState, Decision, DecisionConstraints, ModelOutput


class SafetyStockPolicy:
    def __init__(self, safety_stock_days: float = 1.0) -> None:
        if safety_stock_days < 0:
            raise ValueError("safety_stock_days cannot be negative")
        self.safety_stock_days = safety_stock_days

    def decide(
        self,
        model_output: ModelOutput,
        states: list[BusinessState],
        constraints: DecisionConstraints,
    ) -> list[Decision]:
        decisions: list[Decision] = []
        if model_output.forecast_semantics != "daily_rate":
            raise ValueError("safety-stock policy requires daily-rate forecasts")
        for state in states:
            forecast = model_output.forecasts.get(state.item_key, 0.0)
            target_days = state.lead_time_days + state.review_period_days + self.safety_stock_days
            target_inventory = forecast * target_days
            quantity = max(0.0, target_inventory - state.inventory_position)
            quantity = min(quantity, constraints.max_units)
            if 0 < quantity < constraints.min_order_qty:
                quantity = constraints.min_order_qty
            if state.unit_cost > 0 and quantity * state.unit_cost > constraints.max_spend:
                quantity = constraints.max_spend / state.unit_cost
            quantity = round(quantity, 2)
            if quantity <= 0:
                continue
            spend = round(quantity * state.unit_cost, 2)
            identity = "|".join(
                (model_output.input_snapshot_version, *state.item_key, str(quantity))
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
                    reason_codes=("below_target_inventory", "lead_time_and_review_covered"),
                    expected_effect={"target_inventory": round(target_inventory, 2)},
                    risk_summary="Point forecast baseline; actual demand may vary.",
                    constraints_applied=("max_units", "max_spend", "min_order_qty"),
                    approval_required=spend >= constraints.approval_spend_threshold,
                    expires_at=model_output.generated_at + timedelta(days=1),
                    action_context={
                        "forecast_daily": round(forecast, 4),
                        "inventory_position": round(state.inventory_position, 2),
                        "service_level": constraints.service_level,
                    },
                )
            )
        return decisions

    def explain(self, decision: Decision) -> str:
        return (
            f"Order {decision.quantity:g} units for {decision.node_id}/{decision.sku_id}; "
            f"inventory position was {decision.action_context['inventory_position']:g}."
        )

    def describe(self) -> dict[str, str]:
        return {
            "name": "safety_stock",
            "version": "0.1.0",
            "task": "replenishment",
            "safety_stock_days": str(self.safety_stock_days),
            "limitation": "Uses a point forecast and immediate-arrival replay assumption.",
        }


register_policy(
    "safety_stock",
    SafetyStockPolicy,
    ComponentAsset(
        "policy", "safety_stock", "0.1.0", "ModelOutput+BusinessState+DecisionConstraints",
        "Decision", ("safety_stock_days",), "Demonstration policy; not calibrated for production.",
    ),
)
