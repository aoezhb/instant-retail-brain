# Contributing

Thank you for helping improve `instant-retail-brain`.

## Suitable Changes

Changes should improve the compact data, forecasting, policy, approval, replay, and evaluation flow. Production connectors, customer-specific rules, external write integrations, distributed infrastructure, and real business data belong in customer projects or separately reviewed proposals.

## Development

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
python -m pip install -e ".[test]"
python -m unittest discover -s tests -t . -v
```

Install optional LightGBM support with:

```bash
python -m pip install -e ".[lightgbm]"
```

Keep changes focused, preserve public schemas and interfaces, add a small regression test for changed behavior, and update the relevant documentation. Never commit credentials, customer exports, personal data, or proprietary platform interfaces.

## Pull Requests

Describe the behavior changed, the modules affected, validation performed, and any remaining limitation. A contribution is not production approval: customer deployment still requires data mapping, calibration, authorization, approval, audit, and rollback design.

```mermaid
flowchart LR
    A[Focused change] --> B[Follows public formats and interfaces]
    B --> C[Small regression test]
    C --> D[Documentation update]
    D --> E[Pull request review]
```

## Issues and Proposals

Use the bug report form for reproducible problems in the example flow. Use the component proposal form for a model, policy, metric, scenario, or data-input suggestion. Reports may be written in English or Chinese. Keep customer data, credentials, and confidential operating rules out of public issues.

[Chinese version](CONTRIBUTING.zh-CN.md)
