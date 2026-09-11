# 贡献指南

感谢参与改进 `instant-retail-brain`。

## 适合提交的修改

贡献应改进精简的数据、预测、策略、审批、回放和评估流程。生产连接器、客户专属规则、外部写入、分布式基础设施和真实业务数据应放入客户项目，或作为独立提案审核。

## 开发

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
python -m pip install -e ".[test]"
python -m unittest discover -s tests -t . -v
```

安装可选的 LightGBM 支持：

```bash
python -m pip install -e ".[lightgbm]"
```

修改应保持聚焦，不随意改变公共 Schema 和接口，为行为变化增加小型回归测试，并同步相关文档。禁止提交凭证、客户导出、个人数据或平台私有接口。

## Pull Request

说明最终行为、受影响的模块、验证方式和已知限制。合并贡献不等于生产批准；客户部署仍需完成数据映射、模型校准、授权、审批、审计和回退设计。

```mermaid
flowchart LR
    A[聚焦的修改] --> B[符合公共格式与接口]
    B --> C[小型回归测试]
    C --> D[同步文档]
    D --> E[Pull Request 审核]
```

## 问题与组件建议

可复现的示例流程问题请使用 Bug 报告表单；模型、策略、指标、场景或数据输入建议请使用组件建议表单。可以使用中文或英文填写。请勿在公开 Issue 中提交客户数据、凭证或保密经营规则。

[English version](CONTRIBUTING.md)
