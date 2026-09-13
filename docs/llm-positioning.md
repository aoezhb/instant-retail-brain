# Positioning LLMs and Agents in Replenishment Systems

## Conclusion

For instant-retail replenishment with consistent data definitions, explicit business rules, and strict inventory constraints, an LLM is not a core dependency. Demand forecasts, P50/P90 values, target inventory, order quantities, budget checks, approval decisions, and external writes should be produced by structured data, dedicated forecasting models, deterministic policies, and constraint validators.

This project is not an LLM replenishment system. It is a pluggable, verifiable, and auditable decision pipeline for intelligent replenishment.

## Why the LLM should stay out of the critical path

Replenishment requires repeatability, verifiable constraints, diagnosable failures, and replayable run records. Natural-language generation does not replace these properties and can introduce output drift, missed constraints, uncalibrated forecast intervals, external-service cost, and more difficult auditing.

If operators cannot understand a standardized result, the first fixes should be clearer metric definitions, reason codes, calculation evidence, UI design, and training—not an explanation agent.

## What a transparent decision result looks like

```json
{
  "forecast_p50": 12.4,
  "forecast_p90": 18.7,
  "recommended_order_qty": 15,
  "expected_cost": 60,
  "stockout_risk": 0.12,
  "approval_required": false,
  "constraint_status": "passed",
  "decision_id": "abc-123",
  "reason_codes": ["below_target_inventory", "lead_time_and_review_covered", "max_spend_checked"]
}
```

These fields are more suitable than generated prose for testing, auditing, replay, and system integration.

## Where an LLM may fit

Use an LLM only when it provides a clear benefit at the system boundary: reading supplier documents, assisting cross-system queries, drafting field mappings or rule configurations for human approval, grouping exception tickets, or providing a natural-language query interface.

These capabilities must not modify deterministic forecasts, quantities, budget checks, approval status, or execution results.

## Recommended boundary

```text
Data adapter -> Forecast model -> Replenishment policy -> Constraint validator -> Decision -> Approval -> Executor -> Audit record

Optional LLM reads structured results or peripheral unstructured material
```

An agent should not generate the final order quantity or write directly to ERP, WMS, or OMS. Every external action must pass schema validation, business constraints, and permission approval.

## Implications for this project

The mainline should continue to focus on data adapters, data quality, forecasting and quantile calibration, replenishment policies, business constraints, historical replay, evaluation metrics, decision records, and controlled execution. LLM/Agent support is a long-term optional extension, not the project's primary selling point or replenishment critical path.
