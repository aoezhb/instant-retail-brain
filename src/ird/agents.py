"""Long-term research extension; deliberately excluded from the core pipeline.

The replenishment engine must remain deterministic. This module is for future
peripheral workflows such as unstructured supplier information and exception
triage, not for calculating or approving inventory actions.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Protocol


class DecisionAgent(Protocol):
    """Optional explanation/orchestration layer; it must not calculate orders."""

    def explain(self, run_record: Mapping[str, Any]) -> str: ...

    def orchestrate(self, task: str, run_record: Mapping[str, Any]) -> str: ...


class RuleBasedAgent:
    def explain(self, run_record: Mapping[str, Any]) -> str:
        summary = run_record.get("result_summary", {}).get("aggregate", {})
        return (
            f"The recorded run recommends {summary.get('recommended_order_qty', 0)} units at "
            f"an expected cost of {summary.get('expected_cost', 0)}."
        )

    def orchestrate(self, task: str, run_record: Mapping[str, Any]) -> str:
        return f"Task: {task}. Review the deterministic decision record before taking action."


class OpenAICompatibleAgent:
    """Optional LLM adapter. The deterministic engine remains the source of truth."""

    def __init__(self, model: str, api_key: str, base_url: str | None = None) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("install the research-llm extra to use OpenAICompatibleAgent") from exc
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        kwargs["timeout"] = 30.0
        self.client = OpenAI(**kwargs)
        self.model = model

    def _complete(self, instruction: str, run_record: Mapping[str, Any]) -> str:
        summary = {
            "result_summary": run_record.get("result_summary", {}),
            "metrics": run_record.get("metrics", {}),
            "decisions": [
                {
                    "decision_id": decision.get("decision_id"),
                    "sku_id": decision.get("sku_id"),
                    "quantity": decision.get("quantity"),
                    "estimated_spend": decision.get("estimated_spend"),
                    "approval_required": decision.get("approval_required"),
                    "risk_summary": decision.get("risk_summary"),
                }
                for decision in run_record.get("decisions", [])
            ],
        }
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": "Explain and orchestrate only. Never invent or alter quantities. The deterministic decision record is authoritative."},
                {"role": "user", "content": instruction + "\n" + json.dumps(summary, ensure_ascii=False, default=str)},
            ],
        )
        return response.choices[0].message.content or ""

    def explain(self, run_record: Mapping[str, Any]) -> str:
        return self._complete("Explain this decision record for an operations reviewer.", run_record)

    def orchestrate(self, task: str, run_record: Mapping[str, Any]) -> str:
        return self._complete(f"Prepare an execution checklist for: {task}", run_record)
