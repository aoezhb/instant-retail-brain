# 数据目录

本目录只允许保存合成数据，或经过明确授权和去标识化处理的数据。

```mermaid
flowchart LR
    A[CSV 或 JSON 样例] --> B[FileDataProvider]
    B --> C[RetailDataHandler]
    C --> D{质量与时间校验}
    D -->|通过| E[带版本的 RetailDataset]
    D -->|失败| F[数据质量错误]
```

- `schemas/`：与平台无关的 JSON Schema，包括需求、协变量、库存、门店-仓点绑定、模型输出、决策、审批、执行回执和运行记录。
- `sample/`：可以安全提交到公开仓库的小型样例。

协变量分别保存 `event_time` 和 `available_time`。计划、预报等未来已知变量可以晚于其数据可用时间发生，但模型不能使用 `available_time` 晚于数据快照的记录。

库存记录可以单独携带 `snapshot_time`，但不能晚于数据集快照。样例还包含经营建议策略所需的售价、正常价和临期天数字段。Handler 会生成明确的门店-仓点绑定，并拒绝需求、库存或协变量之间身份不一致的数据。

禁止提交平台凭证、客户地址、真实订单导出、供应商合同或可识别的门店数据。

[English version](README.md)
