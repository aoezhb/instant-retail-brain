from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from ..registry import ComponentAsset, register_policy
from ..schema import BusinessState, Decision, DecisionConstraints, ModelOutput


class StoreRiskPolicy:
    """Aggregate shortage, expiry, and margin-pressure signals at store/node level."""

    def __init__(self, review_threshold: float = 0.35) -> None:
        if not 0 <= review_threshold <= 1:
            raise ValueError("review_threshold must be between 0 and 1")
        self.review_threshold = review_threshold

    def decide(
        self,
        model_output: ModelOutput,
        states: list[BusinessState],
        constraints: DecisionConstraints,
    ) -> list[Decision]:
        grouped: dict[tuple[str, str, str], list[BusinessState]] = defaultdict(list)
        for state in states:
            grouped[(state.business_unit_id, state.store_id, state.node_id)].append(state)

        decisions: list[Decision] = []
        for (business_unit_id, store_id, node_id), store_states in grouped.items():
            item_risks: list[float] = []
            for state in store_states:
                forecast = model_output.forecasts.get(state.item_key, 0.0)
                target = forecast * (state.lead_time_days + state.review_period_days)
                shortage_risk = min(1.0, max(0.0, target - state.inventory_position) / max(target, 1.0))
                expiry_risk = 0.0
                if state.days_to_expiry is not None and state.days_to_expiry <= 3:
                    expected_sales = forecast * max(0, state.days_to_expiry)
                    expiry_risk = min(
                        1.0,
                        max(0.0, state.available_inventory - expected_sales)
                        / max(state.available_inventory, 1.0),
                    )
                margin_pressure = float(
                    state.selling_price > 0 and state.selling_price <= state.unit_cost
                )
                item_risks.append(0.6 * shortage_risk + 0.3 * expiry_risk + 0.1 * margin_pressure)
            score = sum(item_risks) / max(1, len(item_risks))
            action = "review_store_risk" if score >= self.review_threshold else "monitor"
            identity = "|".join(
                (
                    "store_risk", model_output.input_snapshot_version,
                    business_unit_id, store_id, node_id, action,
                )
            )
            decisions.append(
                Decision(
                    decision_id=str(uuid5(NAMESPACE_URL, identity)),
                    decision_type="store_risk",
                    business_unit_id=business_unit_id,
                    store_id=store_id,
                    node_id=node_id,
                    fulfillment_node_id=None,
                    sku_id="*",
                    recommended_action=action,
                    quantity=0.0,
                    estimated_spend=0.0,
                    reason_codes=("shortage", "expiry", "margin_pressure"),
                    expected_effect={"store_risk_score": round(score, 4)},
                    risk_summary="Composite score is illustrative and not customer calibrated.",
                    constraints_applied=("manual_store_review",),
                    approval_required=action == "review_store_risk",
                    expires_at=model_output.generated_at + timedelta(days=1),
                    action_context={"item_count": len(store_states)},
                )
            )
        return decisions

    def explain(self, decision: Decision) -> str:
        return (
            f"{decision.recommended_action} for {decision.store_id}/{decision.node_id}; "
            f"risk score is {decision.expected_effect['store_risk_score']:g}."
        )

    def describe(self) -> dict[str, str]:
        return {
            "name": "store_risk",
            "version": "0.1.0",
            "task": "store_risk",
            "review_threshold": str(self.review_threshold),
            "limitation": "Illustrative composite score without customer calibration.",
        }


register_policy(
    "store_risk",
    StoreRiskPolicy,
    ComponentAsset(
        "policy", "store_risk", "0.1.0", "ModelOutput+BusinessState[]",
        "Decision(store_risk)", ("review_threshold",),
        "Advisory store/node aggregation; no automatic operational action.",
    ),
)
