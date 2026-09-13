# Evaluation Metrics

The evaluation layer separates forecast quality from operating outcomes. Report the following metrics with the dataset version, model version, policy version, and evaluation window.

| Metric | Definition | Interpretation |
|---|---|---|
| MAE | Mean absolute forecast error | Average unit error |
| RMSE | Root mean squared error | Penalizes large misses |
| WAPE | Sum absolute error / sum actual demand | Scale-independent error |
| P50 coverage | Share of actuals <= P50 | Calibration check for the median |
| P90 coverage | Share of actuals <= P90 | Service-oriented calibration check |
| Stockout rate | 1 - fill rate | Outcome risk in replay |
| Inventory turnover | Served units / average inventory | Capital efficiency proxy |
| Average inventory | Mean inventory held during evaluation | Working-capital exposure |
| Order amount | Sum of accepted decision spend | Procurement commitment |
| Executor rejection rate | Rejected decisions / total decisions | Combined constraint, approval, expiry, and execution rejection signal |
| Approval-required rate | Approval-required decisions / total decisions | Human-control workload |

The current reference implementation uses deterministic synthetic data and a simplified replay. Customer projects must define the evaluation window, returns/cancellations treatment, lost-sales policy, inventory valuation, and approval denominator before comparing runs.

In the current demo, forecast metrics compare each item's predicted daily rate with its mean observed daily demand in the holdout window. Production evaluation should score every forecast origin, horizon, and item separately before aggregation; the demo metric is a compact contract example, not a complete calibration study.
