# Replacing the Demand Model with LightGBM

This project does not hard-code one forecasting algorithm into replenishment. Data preparation returns <code>RetailDataset</code>, every model returns <code>ModelOutput</code>, and downstream policies read that shared format. Moving from a moving average to LightGBM therefore does not require rewriting historical replay, decision validation, or run recording.

## Shortest Working Command

LightGBM is an optional dependency:

~~~bash
python -m pip install -e ".[lightgbm,test]"
python -m ird demo --model lightgbm --policy quantile_replenishment
~~~

The first command installs LightGBM support. The second selects the registered model name while retaining the same synthetic data, quantile replenishment policy, historical replay, and run record.

~~~mermaid
flowchart LR
    A[RetailDataset] --> B{Select model}
    B --> C[Moving Average]
    B --> D[Holt]
    B --> E[Covariate Quantile]
    B --> F[LightGBM]
    C --> G[ModelOutput]
    D --> G
    E --> G
    F --> G
    G --> H[DecisionPolicy]
    H --> I[Validation, replay, and recording]
~~~

## The Model Interface Does Not Change

Every forecasting model provides three methods:

| Method | Purpose |
|---|---|
| <code>fit(dataset)</code> | Train from a specified data snapshot |
| <code>predict(dataset, as_of)</code> | Produce shared forecast output at a specified time |
| <code>describe()</code> | Return the model name, parameters, input version, and limitations |

The LightGBM implementation returns <code>ModelOutput</code> containing:

- Point forecasts by item.
- Quantile forecasts such as P10, P50, and P90.
- Forecast scope.
- Input snapshot version.
- Generation time and forecast horizon.

The policy does not need to know whether the model uses trees, linear regression, or a moving average.

## Features Used by the Current LightGBM Example

The sample fits one global model across multiple items with these features:

| Feature | Source |
|---|---|
| Item index | <code>ItemKey</code> values in the training data |
| Day of week | Prediction date |
| Weekend flag | Time covariate |
| Promotion flag | Operating covariate |
| Holiday flag | Calendar covariate |
| Temperature | External covariate |
| Previous demand | Available demand history |
| Seven-day rolling mean | Available demand history |

Training rows use only demand and covariates available at the historical event time. A covariate whose <code>available_time</code> is later than the sample time is not read early.

## How Point and Quantile Models Are Trained

The current implementation trains a small set of estimators:

1. A point model with the <code>regression_l1</code> objective.
2. One <code>quantile</code> model for every requested quantile.
3. Negative predictions are clipped to zero.
4. Quantile results are ordered from low to high so P90 cannot remain below P50.

Default parameters are:

~~~text
n_estimators = 100
learning_rate = 0.05
num_leaves = 15
quantiles = (0.1, 0.5, 0.9)
horizon_days = 1
random_state = 42
~~~

The CLI uses those defaults. Code-driven experiments can construct the model directly:

~~~python
from ird.models import LightGBMDemandModel

model = LightGBMDemandModel(
    n_estimators=300,
    learning_rate=0.03,
    num_leaves=31,
    quantiles=(0.1, 0.5, 0.9),
)
model.fit(dataset)
output = model.predict(dataset, as_of)
~~~

These numbers only illustrate the call. Customer data requires rolling historical validation to choose parameters.

## What Registration Provides

The model module calls <code>register_model</code> when loaded, recording the model name, factory, input, output, parameters, and limitations. Runtime code retrieves it by name:

~~~python
from ird.registry import get_model

model = get_model("lightgbm")
~~~

Model selection changes while downstream functions continue receiving the same data type. A custom model can register under a new name as long as it implements the public model interface and returns a valid <code>ModelOutput</code>.

## Checks Still Required After Replacement

Successful integration does not prove that a model is ready for operating decisions. At minimum, verify:

1. Training, validation, and replay follow time order.
2. Promotion, price, and weather fields are actually available at prediction time.
3. New items, out-of-stock periods, and abnormal sales have defined handling.
4. Point error and quantile coverage are evaluated separately.
5. Store or node forecast scope matches the replenishment target.
6. Parameters, data versions, and stored model files can be traced to a run record.

## Limits of the Current Example

- It supports a one-day forecast horizon.
- Item indices come from the fitted dataset and do not handle new items after training.
- It does not save or load fitted model files.
- It does not run hyperparameter search or rolling cross-validation.
- The synthetic dataset is too small for algorithm ranking.
- The feature list demonstrates input structure rather than a final customer feature table.

The value of LightGBM here is not a claim that it always beats simple models. It demonstrates that a more advanced model can be integrated, tested, and replaced without rewriting the decision process.

## Related Implementation

- [LightGBM model](../../src/ird/models/lightgbm.py)
- [Model registration and lookup](../../src/ird/registry.py)
- [Public model interface](../../src/ird/interfaces.py)
- [LightGBM and probabilistic-output tests](../../tests/extension/test_advanced_components.py)
- [Model registry tests](../../tests/unit/test_model_policy_registry.py)
- [Model and algorithm selection guide](../models/model_and_algorithm_selection_guide.md)
- [Architecture](../architecture.md)

[Chinese version](replacing-the-demand-model-with-lightgbm.zh-CN.md)
