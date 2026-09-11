from __future__ import annotations

from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from ..registry import ComponentAsset, register_policy
from ..schema import BusinessState, Decision, DecisionConstraints, ModelOutput


class RiskAdjustedAssortmentPolicy:
    """Score SKU retention from forecast margin, holding cost, and excess cover."""

    def __init__(
        self,
        minimum_score: float = 0.0,
        holding_cost_rate: float = 0.02,
        maximum_cover_days: float = 14.0,
    ) -> None:
        if holding_cost_rate < 0 or maximum_cover_days <= 0:
            raise ValueError("holding cost and cover parameters must be valid")
        self.minimum_score = minimum_score
        self.holding_cost_rate = holding_cost_rate
        self.maximum_cover_days = maximum_cover_days

    def decide(
        self,
        model_output: ModelOutput,
        states: list[BusinessState],
        constraints: DecisionConstraints,
    ) -> list[Decision]:
        decisions: list[Decision] = []
        for state in states:
            forecast = model_output.forecasts.get(state.item_key, 0.0)
            margin = max(0.0, state.selling_price - state.unit_cost)
            inventory = max(0.0, state.inventory_position)
            cover_days = inventory / max(forecast, 0.01)
            holding_cost = inventory * state.unit_cost * self.holding_cost_rate
            excess_units = max(0.0, inventory - forecast * self.maximum_cover_days)
            excess_cover_cost = excess_units * state.unit_cost * self.holding_cost_rate
            score = forecast * margin - holding_cost - excess_cover_cost
            action = "retain" if score >= self.minimum_score else "review_delist"
            identity = "|".join(
                ("risk_adjusted_assortment", model_output.input_snapshot_version, *state.item_key, action)
            )
            decisions.append(
                Decision(
                    decision_id=str(uuid5(NAMESPACE_URL, identity)),
                    decision_type="assortment",
                    business_unit_id=state.business_unit_id,
                    store_id=state.store_id,
                    node_id=state.node_id,
                    fulfillment_node_id=None,
                    sku_id=state.sku_id,
                    recommended_action=action,
                    quantity=0.0,
                    estimated_spend=0.0,
                    reason_codes=("risk_adjusted_score", "inventory_cover"),
                    expected_effect={"assortment_score": round(score, 4)},
                    risk_summary="Score omits substitution, traffic, and strategic assortment effects.",
                    constraints_applied=("manual_assortment_review",),
                    approval_required=True,
                    expires_at=model_output.generated_at + timedelta(days=7),
                    action_context={
                        "forecast_daily": round(forecast, 4),
                        "gross_margin_per_unit": round(margin, 2),
                        "inventory_cover_days": round(cover_days, 2),
                    },
                )
            )
        return decisions

    def explain(self, decision: Decision) -> str:
        return (
            f"{decision.recommended_action} {decision.node_id}/{decision.sku_id}; "
            f"risk-adjusted score is {decision.expected_effect['assortment_score']:g}."
        )

    def describe(self) -> dict[str, str]:
        return {
            "name": "risk_adjusted_assortment",
            "version": "0.1.0",
            "task": "assortment",
            "minimum_score": str(self.minimum_score),
            "holding_cost_rate": str(self.holding_cost_rate),
            "maximum_cover_days": str(self.maximum_cover_days),
            "limitation": "Decision is advisory and requires customer-specific economics.",
        }


register_policy(
    "risk_adjusted_assortment",
    RiskAdjustedAssortmentPolicy,
    ComponentAsset(
        "policy", "risk_adjusted_assortment", "0.1.0", "ModelOutput+BusinessState",
        "Decision(assortment)", ("minimum_score", "holding_cost_rate", "maximum_cover_days"),
        "Advisory score only; substitution and strategic assortment constraints are excluded.",
    ),
)
