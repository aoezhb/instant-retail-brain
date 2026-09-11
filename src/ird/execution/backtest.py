from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..schema import ApprovalRecord, Decision, DecisionConstraints, ExecutionReceipt


ALLOWED_ACTIONS = {
    "replenishment": {"order"},
    "assortment": {"retain", "review_delist"},
    "pricing": {"markdown", "restore_price"},
    "store_risk": {"monitor", "review_store_risk"},
}


@dataclass(frozen=True)
class ExecutionBatch:
    accepted: tuple[Decision, ...]
    receipts: tuple[ExecutionReceipt, ...]
    approvals: tuple[ApprovalRecord, ...] = ()


class BacktestExecutor:
    def execute(
        self,
        decisions: list[Decision],
        constraints: DecisionConstraints,
        executed_at: datetime,
        approvals: list[ApprovalRecord] | None = None,
    ) -> ExecutionBatch:
        if executed_at.tzinfo is None or executed_at.utcoffset() is None:
            raise ValueError("executed_at must be timezone-aware")
        decision_ids = [decision.decision_id for decision in decisions]
        if len(set(decision_ids)) != len(decision_ids):
            raise ValueError("duplicate decision_id in execution batch")
        approvals = approvals or []
        approval_by_decision = {approval.decision_id: approval for approval in approvals}
        if len(approval_by_decision) != len(approvals):
            raise ValueError("duplicate approval record for decision")
        accepted: list[Decision] = []
        receipts: list[ExecutionReceipt] = []
        used_units = 0.0
        used_spend = 0.0
        for decision in decisions:
            reason = self._reject_reason(
                decision,
                constraints,
                executed_at,
                approval_by_decision,
                used_units,
                used_spend,
            )
            status = "rejected" if reason else "accepted"
            if not reason:
                accepted.append(decision)
                if decision.decision_type == "replenishment":
                    used_units += decision.quantity
                used_spend += decision.estimated_spend
                reason = "validated for backtest"
            receipts.append(ExecutionReceipt(decision.decision_id, status, reason, executed_at))
        return ExecutionBatch(tuple(accepted), tuple(receipts), tuple(approvals))

    @staticmethod
    def _reject_reason(
        decision: Decision,
        constraints: DecisionConstraints,
        executed_at: datetime,
        approval_by_decision: dict[str, ApprovalRecord],
        used_units: float,
        used_spend: float,
    ) -> str:
        allowed_actions = ALLOWED_ACTIONS.get(decision.decision_type)
        if allowed_actions is None:
            return "unknown decision type"
        if decision.recommended_action not in allowed_actions:
            return "action is not valid for decision type"
        if decision.expires_at < executed_at:
            return "decision expired"
        if decision.quantity < 0 or decision.quantity > constraints.max_units:
            return "quantity constraint violated"
        if (
            decision.decision_type == "replenishment"
            and 0 < decision.quantity < constraints.min_order_qty
        ):
            return "minimum order quantity violated"
        if decision.estimated_spend < 0 or decision.estimated_spend > constraints.max_spend:
            return "spend constraint violated"
        if (
            decision.decision_type == "replenishment"
            and used_units + decision.quantity > constraints.max_units
        ):
            return "batch quantity constraint violated"
        if used_spend + decision.estimated_spend > constraints.max_spend:
            return "batch spend constraint violated"
        if (
            decision.estimated_spend >= constraints.approval_spend_threshold
            and not decision.approval_required
        ):
            return "approval flag required"
        if decision.approval_required:
            approval = approval_by_decision.get(decision.decision_id)
            if approval is None:
                return "approval required"
            if approval.status != "approved":
                return "approval rejected"
            if approval.decided_at > executed_at:
                return "approval occurs after execution time"
        external_write = decision.action_context.get("external_write", False)
        if not isinstance(external_write, bool):
            return "external_write flag must be boolean"
        if external_write and not constraints.allow_external_write:
            return "external write not allowed"
        return ""


def validate_decisions(
    decisions: list[Decision],
    constraints: DecisionConstraints,
    executed_at: datetime,
    approvals: list[ApprovalRecord] | None = None,
) -> list[Decision]:
    return list(
        BacktestExecutor().execute(
            decisions, constraints, executed_at, approvals
        ).accepted
    )
