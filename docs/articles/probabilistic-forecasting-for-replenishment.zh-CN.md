# 概率预测如何驱动补货

补货并不只关心“明天平均卖多少”，还关心需求超过预测值的可能性。点预测给出一个代表值，概率预测则描述不同需求水平出现的范围。补货策略可以据此选择服务水平，并把缺货风险和库存占用之间的取舍写进计算过程。

本项目使用分位数表达概率预测。例如：

~~~text
P10 = 5
P50 = 9
P90 = 16
~~~

其含义是预测分布中约 10%、50%、90% 的结果不高于对应数值。P50 接近中位需求，P90 更保守，通常会产生更高的备货目标。

## 从预测到补货的计算过程

~~~mermaid
flowchart LR
    A[历史需求与可用协变量] --> B[概率预测模型]
    B --> C[P10 / P50 / P90]
    C --> D[选择服务水平]
    D --> E[计算覆盖期需求]
    E --> F[减去库存位置]
    F --> G[应用数量与金额限制]
    G --> H[补货建议]
~~~

这个过程包含四个关键量：

1. 需求分位数。
2. 服务水平。
3. 采购提前期与复核周期。
4. 当前库存位置。

## 第一步：选择需求分位数

<code>DecisionConstraints.service_level</code> 表示策略希望采用的服务水平。当前示例默认使用 0.90，并在模型提供的分位数中选择不低于目标的最小分位数。

例如模型输出 P10、P50、P90，而服务水平为 0.90，策略选择 P90。如果目标是 0.85，也会选择 P90，因为示例没有 P85。

如果目标高于模型已有的最大分位数，当前示例会使用最大可用分位数。实际项目应明确这是允许降级、拒绝计算，还是要求模型补充相应分位数。

## 第二步：计算需要覆盖的天数

策略把采购提前期与复核周期相加：

~~~text
protection_days = lead_time_days + review_period_days
~~~

提前期表示下单到到货的等待时间，复核周期表示两次补货计算之间的间隔。库存目标需要覆盖这两个阶段。

如果只有点预测，示例使用：

~~~text
target_inventory = daily_point_forecast * protection_days
~~~

如果模型提供中位数和目标分位数，示例先估算日需求标准差，再按照每日需求相互独立的近似计算累计需求分位数：

~~~text
daily_std = (daily_quantile - daily_median) / z(q)

target_inventory =
    daily_median * protection_days
    + z(q) * daily_std * sqrt(protection_days)
~~~

这里的 <code>z(q)</code> 是标准正态分布在分位数 <code>q</code> 下的取值。这是一个便于演示的近似，不等同于直接预测整个提前期累计需求。

## 第三步：扣除库存位置

补货不能只看当前可用库存，还要考虑在途、预留和欠单：

~~~text
inventory_position =
    available_inventory
    + on_order
    - reserved_inventory
    - backorders
~~~

随后计算：

~~~text
order_qty = max(0, target_inventory - inventory_position)
~~~

这种写法避免在已有在途订单时重复补货，也不会把已经预留或欠交的数量误认为可自由使用。

## 第四步：应用实际限制

概率预测只回答需求风险，不能单独决定最终下单量。当前策略随后处理：

- 最大补货数量 <code>max_units</code>。
- 最大预计金额 <code>max_spend</code>。
- 最小下单量 <code>min_order_qty</code>。
- 超过金额阈值时需要人工审批。

最终 <code>Decision</code> 还会记录使用的分位数、累计需求目标、库存位置、预计金额和应用过的限制，便于解释计算结果。

## 当前示例的一次实际结果

确定性合成数据中的一个商品产生了以下结果：

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

这个结果只用于说明字段如何连接，不代表行业基准或模型精度。

## 为什么不能只提高服务水平

服务水平越高，通常需要选择越高的需求分位数，库存目标也随之上升。但更高库存可能增加资金占用、损耗和临期风险。因此服务水平应按商品类别、毛利、供应稳定性、保质期和缺货代价设置，而不是所有商品统一使用一个最高值。

概率补货还依赖两个前提：

1. 分位数经过校准，例如预测 P90 的实际覆盖率应接近 90%。
2. 预测数据在当时确实可获得，不能把未来活动或事后修正数据带入历史训练。

## 当前实现的适用范围

当前实现适合展示“分位数预测如何进入补货策略”，但仍有以下限制：

- 只处理单日 <code>daily_rate</code> 预测。
- 使用每日需求相互独立的累计近似。
- 没有直接训练提前期累计需求。
- 没有按商品成本结构自动计算最优服务水平。
- 合成数据不能证明真实业务中的预测精度。

客户项目通常需要增加分位数校准、滚动历史验证、供应波动、最小包装量、订货日历和多级库存处理。

## 对应实现

- [概率补货策略](../../src/ird/policies/quantile_replenishment.py)
- [ModelOutput、BusinessState 与 DecisionConstraints](../../src/ird/schema.py)
- [概率模型与策略测试](../../tests/extension/test_advanced_components.py)
- [需求协变量与概率预测](../demand_covariates_and_probabilistic_forecasting.zh-CN.md)
- [模型与算法选型指南](../models/model_and_algorithm_selection_guide.zh-CN.md)

[English version](probabilistic-forecasting-for-replenishment.md)
