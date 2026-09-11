# 如何把需求模型替换为 LightGBM

这个项目没有把预测算法写死在补货流程中。数据处理输出 <code>RetailDataset</code>，预测模型输出 <code>ModelOutput</code>，后续策略只读取统一格式。因此从移动平均切换到 LightGBM 时，历史回放、决策检查和运行记录不需要一起重写。

## 最短运行方式

LightGBM 是可选依赖：

~~~bash
python -m pip install -e ".[lightgbm,test]"
python -m ird demo --model lightgbm --policy quantile_replenishment
~~~

第一条命令安装 LightGBM 支持，第二条命令通过已注册名称选择模型。CLI 仍然使用同一套合成数据、概率补货策略、历史回放和结果记录。

~~~mermaid
flowchart LR
    A[RetailDataset] --> B{选择模型}
    B --> C[Moving Average]
    B --> D[Holt]
    B --> E[Covariate Quantile]
    B --> F[LightGBM]
    C --> G[ModelOutput]
    D --> G
    E --> G
    F --> G
    G --> H[DecisionPolicy]
    H --> I[检查、回放与记录]
~~~

## 模型接口保持不变

所有预测模型都提供三个方法：

| 方法 | 作用 |
|---|---|
| <code>fit(dataset)</code> | 使用指定数据快照训练 |
| <code>predict(dataset, as_of)</code> | 在给定时间点生成统一预测结果 |
| <code>describe()</code> | 返回模型名称、参数、输入版本和使用限制 |

LightGBM 实现仍然返回 <code>ModelOutput</code>，其中包含：

- 商品级点预测。
- P10、P50、P90 等分位数预测。
- 预测范围 <code>forecast_scope</code>。
- 输入数据版本。
- 生成时间和预测天数。

策略不需要知道模型内部使用的是树模型、线性回归还是移动平均。

## 当前 LightGBM 使用哪些特征

示例将多个商品放入一个全局模型，使用以下特征：

| 特征 | 来源 |
|---|---|
| 商品索引 | 训练数据中的 <code>ItemKey</code> |
| 星期 | 预测日期 |
| 周末标记 | 时间协变量 |
| 促销标记 | 业务协变量 |
| 节假日标记 | 日历协变量 |
| 温度 | 外部协变量 |
| 前一日需求 | 可用历史需求 |
| 近 7 日平均需求 | 可用历史需求 |

训练样本只读取当时已经可获得的需求和协变量。<code>available_time</code> 晚于样本时间的信息不会被提前使用。

## 点预测和分位数如何训练

当前实现训练一组模型：

1. 使用 <code>regression_l1</code> 目标训练点预测模型。
2. 为每个指定分位数分别训练 <code>quantile</code> 模型。
3. 推理后将负预测截断为零。
4. 按分位数从低到高整理结果，避免 P90 低于 P50 之类的交叉输出。

默认参数为：

~~~text
n_estimators = 100
learning_rate = 0.05
num_leaves = 15
quantiles = (0.1, 0.5, 0.9)
horizon_days = 1
random_state = 42
~~~

CLI 使用默认参数。需要调整参数时，可在 Python 流程中直接创建 <code>LightGBMDemandModel</code>：

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

这些数字只是调用示例，客户数据需要通过滚动历史验证选择参数。

## 注册信息有什么作用

模型模块加载时调用 <code>register_model</code>，登记模型名称、创建方式、输入输出、参数和限制。运行程序根据名称取得模型：

~~~python
from ird.registry import get_model

model = get_model("lightgbm")
~~~

因此替换模型只改变组件选择，不改变后续函数接收的数据类型。自定义模型也可以使用新的名称注册，只要实现公共模型接口并返回合法的 <code>ModelOutput</code>。

## 替换模型时仍需检查什么

能够接入流程不代表模型已经适合真实经营。至少需要检查：

1. 训练、验证和回放严格按时间顺序进行。
2. 促销、价格和天气字段在预测时确实可获得。
3. 新商品、断货商品和异常销量有明确处理方式。
4. 点预测误差和分位数覆盖率分别评估。
5. 模型输出的门店或仓点范围与补货对象一致。
6. 参数、数据版本和模型文件可以对应到一次运行记录。

## 当前示例的限制

- 只支持单日预测。
- 商品索引来自本次训练数据，不处理训练后新增商品。
- 没有模型文件保存和加载。
- 没有超参数搜索或滚动交叉验证。
- 合成数据规模太小，不能用于比较算法优劣。
- 特征仅用于说明输入方式，不代表客户项目的最终特征表。

LightGBM 在这里的价值不是宣称它一定优于简单模型，而是证明较复杂的模型可以在不改写决策流程的情况下被接入、测试和替换。

## 对应实现

- [LightGBM 模型](../../src/ird/models/lightgbm.py)
- [模型注册与查找](../../src/ird/registry.py)
- [公共模型接口](../../src/ird/interfaces.py)
- [LightGBM 与概率输出测试](../../tests/extension/test_advanced_components.py)
- [模型注册测试](../../tests/unit/test_model_policy_registry.py)
- [模型与算法选型指南](../models/model_and_algorithm_selection_guide.zh-CN.md)
- [架构说明](../architecture.zh-CN.md)

[English version](replacing-the-demand-model-with-lightgbm.md)
