from __future__ import annotations

from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from ..registry import ComponentAsset, register_policy
from ..schema import BusinessState, Decision, DecisionConstraints, ModelOutput


class ExpiryMarkdownPolicy:
    """Recommend a rate-limited markdown when expected demand cannot clear expiring stock."""

    def __init__(
        self,
        trigger_days: int = 3,
        minimum_markdown: float = 0.1,
        maximum_markdown: float = 0.4,
    ) -> None:
        if trigger_days < 1 or not 0 <= minimum_markdown <= maximum_markdown < 1:
            raise ValueError("markdown parameters must be valid")
        self.trigger_days = trigger_days
        self.minimum_markdown = minimum_markdown
        self.maximum_markdown = maximum_markdown

    def decide(
        self,
        model_output: ModelOutput,
        states: list[BusinessState],
        constraints: DecisionConstraints,
    ) -> list[Decision]:
        decisions: list[Decision] = []
        for state in states:
            if state.selling_price <= 0 or state.days_to_expiry is None:
                continue
            if state.days_to_expiry <= 0:
                continue
            if state.days_to_expiry > self.trigger_days:
                if state.regular_price > state.selling_price:
                    decisions.append(self._price_recovery(model_output, state))
                continue
            forecast = model_output.forecasts.get(state.item_key, 0.0)
            at_risk_units = max(
                0.0, state.available_inventory - forecast * max(1, state.days_to_expiry)
            )
            if at_risk_units <= 0:
                continue
            urgency = (self.trigger_days - state.days_to_expiry + 1) / self.trigger_days
            markdown = min(
                self.maximum_markdown,
                self.minimum_markdown
                + urgency * (self.maximum_markdown - self.minimum_markdown),
            )
            recommended_price = max(state.unit_cost, state.selling_price * (1 - markdown))
            effective_markdown = 1 - recommended_price / state.selling_price
            quantity = round(min(at_risk_units, constraints.max_units), 2)
            identity = "|".join(
                ("expiry_markdown", model_output.input_snapshot_version, *state.item_key, str(quantity))
            )
            decisions.append(
                Decision(
                    decision_id=str(uuid5(NAMESPACE_URL, identity)),
                    decision_type="pricing",
                    business_unit_id=state.business_unit_id,
                    store_id=state.store_id,
                    node_id=state.node_id,
                    fulfillment_node_id=None,
                    sku_id=state.sku_id,
                    recommended_action="markdown",
                    quantity=quantity,
                    estimated_spend=0.0,
                    reason_codes=("expiry_risk", "excess_inventory"),
                    expected_effect={
                        "recommended_price": round(recommended_price, 2),
                        "markdown_rate": round(effective_markdown, 4),
                        "at_risk_units": round(at_risk_units, 2),
                    },
                    risk_summary="Demand elasticity and competitor reactions are not estimated.",
                    constraints_applied=("unit_cost_price_floor", "maximum_markdown"),
                    approval_required=True,
                    expires_at=model_output.generated_at + timedelta(days=1),
                    action_context={
                        "current_price": state.selling_price,
                        "days_to_expiry": state.days_to_expiry,
                        "forecast_daily": round(forecast, 4),
                    },
                )
            )
        return decisions

    @staticmethod
    def _price_recovery(model_output: ModelOutput, state: BusinessState) -> Decision:
        identity = "|".join(
            ("price_recovery", model_output.input_snapshot_version, *state.item_key)
        )
        return Decision(
            decision_id=str(uuid5(NAMESPACE_URL, identity)),
            decision_type="pricing",
            business_unit_id=state.business_unit_id,
            store_id=state.store_id,
            node_id=state.node_id,
            fulfillment_node_id=None,
            sku_id=state.sku_id,
            recommended_action="restore_price",
            quantity=0.0,
            estimated_spend=0.0,
            reason_codes=("expiry_window_cleared", "regular_price_available"),
            expected_effect={"recommended_price": round(state.regular_price, 2)},
            risk_summary="Price recovery remains advisory and excludes elasticity effects.",
            constraints_applied=("regular_price_ceiling",),
            approval_required=True,
            expires_at=model_output.generated_at + timedelta(days=1),
            action_context={
                "current_price": state.selling_price,
                "regular_price": state.regular_price,
                "days_to_expiry": state.days_to_expiry,
            },
        )

    def explain(self, decision: Decision) -> str:
        if decision.recommended_action == "restore_price":
            return (
                f"Restore {decision.sku_id} to regular price "
                f"{decision.expected_effect['recommended_price']:g}."
            )
        return (
            f"Markdown {decision.sku_id} to {decision.expected_effect['recommended_price']:g}; "
            f"{decision.expected_effect['at_risk_units']:g} units are at risk."
        )

    def describe(self) -> dict[str, str]:
        return {
            "name": "expiry_markdown",
            "version": "0.1.0",
            "task": "pricing",
            "trigger_days": str(self.trigger_days),
            "minimum_markdown": str(self.minimum_markdown),
            "maximum_markdown": str(self.maximum_markdown),
            "limitation": "Rule-based markdown and recovery without elasticity estimation.",
        }


register_policy(
    "expiry_markdown",
    ExpiryMarkdownPolicy,
    ComponentAsset(
        "policy", "expiry_markdown", "0.1.0", "ModelOutput+BusinessState(expiry+price)",
        "Decision(pricing)", ("trigger_days", "minimum_markdown", "maximum_markdown"),
        "Advisory markdown/recovery; no elasticity or platform write integration.",
    ),
)
