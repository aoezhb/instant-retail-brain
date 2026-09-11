# How Probabilistic Forecasting Drives Replenishment

Replenishment needs more than an estimate of average demand. It also needs to consider the chance that demand will exceed that estimate. A point forecast supplies one representative value. A probabilistic forecast describes a range of possible demand levels, allowing a policy to state the tradeoff between shortage risk and inventory investment.

This project represents probability with quantiles. For example:

~~~text
P10 = 5
P50 = 9
P90 = 16
~~~

Approximately 10, 50, and 90 percent of the forecast distribution lie at or below the corresponding values. P50 is close to median demand. P90 is more conservative and generally produces a higher inventory target.

## From Forecast to Order Quantity

~~~mermaid
flowchart LR
    A[History and available covariates] --> B[Probabilistic model]
    B --> C[P10 / P50 / P90]
    C --> D[Select service level]
    D --> E[Calculate protection-period demand]
    E --> F[Subtract inventory position]
    F --> G[Apply quantity and spend limits]
    G --> H[Replenishment decision]
~~~

The calculation uses four central inputs:

1. Demand quantiles.
2. Target service level.
3. Lead time and review period.
4. Current inventory position.

## Step 1: Select a Demand Quantile

<code>DecisionConstraints.service_level</code> states the service level requested by the policy. The current sample defaults to 0.90 and selects the smallest model quantile that is not below the target.

If the model provides P10, P50, and P90 and the service target is 0.90, the policy selects P90. A target of 0.85 also selects P90 because the sample has no P85 output.

If the target is above the largest available model quantile, the current sample uses the largest available quantile. A production implementation should decide explicitly whether to permit that fallback, reject the calculation, or require the model to provide the requested quantile.

## Step 2: Calculate the Protection Period

The policy adds purchasing lead time and the replenishment review period:

~~~text
protection_days = lead_time_days + review_period_days
~~~

Lead time is the delay between ordering and arrival. The review period is the interval before the next replenishment calculation. The inventory target needs to cover both.

With only a point forecast, the sample uses:

~~~text
target_inventory = daily_point_forecast * protection_days
~~~

When median and target quantiles are available, the sample estimates daily standard deviation and approximates a cumulative quantile under independent daily demand:

~~~text
daily_std = (daily_quantile - daily_median) / z(q)

target_inventory =
    daily_median * protection_days
    + z(q) * daily_std * sqrt(protection_days)
~~~

<code>z(q)</code> is the standard-normal value for quantile <code>q</code>. This is a compact demonstration approximation, not a direct model of total demand across the whole lead time.

## Step 3: Subtract Inventory Position

The calculation needs more than available stock. It also accounts for inbound stock, reservations, and backorders:

~~~text
inventory_position =
    available_inventory
    + on_order
    - reserved_inventory
    - backorders
~~~

The preliminary order quantity is:

~~~text
order_qty = max(0, target_inventory - inventory_position)
~~~

This prevents another order from being raised as if existing inbound stock did not exist, and it avoids treating reserved or already owed stock as freely available.

## Step 4: Apply Operating Limits

Probability describes demand risk but does not determine the final order by itself. The sample then applies:

- Maximum units through <code>max_units</code>.
- Maximum estimated spend through <code>max_spend</code>.
- Minimum order quantity through <code>min_order_qty</code>.
- Human approval when estimated spend reaches the approval threshold.

The resulting <code>Decision</code> records the selected quantile, cumulative demand target, inventory position, estimated spend, and applied limits.

## One Result from the Current Demo

One SKU in the deterministic synthetic sample produces:

~~~json
{
  "point_forecast": 5.3558,
  "p50": 5.3558,
  "p90": 5.626,
  "selected_quantile": 0.9,
  "cumulative_demand_quantile": 21.9636,
  "inventory_position": 4.0,
  "order_quantity": 17.96
}
~~~

These values demonstrate how the fields connect. They are not an industry benchmark or an accuracy claim.

## Why the Highest Service Level Is Not Always Best

A higher service level generally selects a higher demand quantile and raises the inventory target. That can reduce shortage exposure while increasing working capital, waste, and expiry risk. Service levels should therefore reflect item category, margin, supply reliability, shelf life, and shortage cost rather than applying one maximum value to every SKU.

Probabilistic replenishment also depends on two conditions:

1. Quantiles should be calibrated, so realized coverage is reasonably close to the stated level.
2. Training inputs must have been available at the historical prediction time.

## Scope of the Current Implementation

The current implementation demonstrates how forecast quantiles enter a replenishment policy, with these limitations:

- It consumes one-day <code>daily_rate</code> forecasts.
- It approximates cumulative demand under independent daily demand.
- It does not predict lead-time demand directly.
- It does not optimize service levels from SKU-specific cost.
- Synthetic data cannot establish real-world forecast accuracy.

A customer implementation commonly adds quantile calibration, rolling historical validation, supply variability, pack sizes, ordering calendars, and multi-level inventory.

## Related Implementation

- [Quantile replenishment policy](../../src/ird/policies/quantile_replenishment.py)
- [ModelOutput, BusinessState, and DecisionConstraints](../../src/ird/schema.py)
- [Probabilistic model and policy tests](../../tests/extension/test_advanced_components.py)
- [Demand covariates and probabilistic forecasting](../demand_covariates_and_probabilistic_forecasting.md)
- [Model and algorithm selection guide](../models/model_and_algorithm_selection_guide.md)

[Chinese version](probabilistic-forecasting-for-replenishment.zh-CN.md)
