from __future__ import annotations

import json
import csv
import io
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from importlib.util import find_spec

from ird.cli import run_dataset_demo, run_demo
from ird.data.handler import RetailDataHandler
from ird.registry import list_components


st.set_page_config(page_title="instant-retail-brain", layout="wide")
st.title("instant-retail-brain")
st.caption("可插拔、可验证、可审计的即时零售智能补货决策流水线")

with st.sidebar:
    st.header("运行参数")
    available_models = ["moving_average", "holt_trend"]
    if find_spec("lightgbm") is not None:
        available_models.append("lightgbm")
    model_name = st.selectbox("模型", available_models, index=0)
    policies = [
        name
        for name in list_components()["policies"]
        if name in {"safety_stock", "quantile_replenishment"}
    ]
    policy_name = st.selectbox(
        "补货策略", policies, index=policies.index("safety_stock")
    )
    uploaded = st.file_uploader("上传销售 CSV（可选）", type=["csv"])
    inventory_uploaded = st.file_uploader("上传库存 JSON（上传 CSV 时必需）", type=["json"])
    run = st.button("运行演示", type="primary")

if uploaded is not None:
    st.info(
        "CSV 需要至少两个需求日期，并同时上传训练截止日当日或更早的历史库存 JSON；"
        "两者必须使用相同的业务单元、门店、仓点和 SKU。"
    )

if run or "payload" not in st.session_state:
    try:
        if uploaded is None:
            st.session_state.payload = run_demo(model_name, policy_name)
        else:
            if inventory_uploaded is None:
                raise ValueError("上传需求 CSV 时还需要上传库存 JSON")
            rows = list(csv.DictReader(io.StringIO(uploaded.getvalue().decode("utf-8-sig"))))
            inventory = json.loads(inventory_uploaded.getvalue().decode("utf-8-sig"))
            dataset = RetailDataHandler().build_dataset(rows, inventory, datetime.now(timezone.utc))
            st.session_state.payload = run_dataset_demo(dataset, model_name, policy_name)
    except (KeyError, RuntimeError, ValueError) as exc:
        st.error(str(exc))
        st.stop()

payload = st.session_state.payload
summary = payload.get("result_summary", {})
aggregate = summary.get("aggregate", {})
metrics = payload.get("metrics", {})

cols = st.columns(4)
cols[0].metric("建议订货量", aggregate.get("recommended_order_qty", 0))
cols[1].metric("预计金额", aggregate.get("expected_cost", 0))
cols[2].metric("缺货风险", aggregate.get("stockout_risk", 0))
cols[3].metric("约束状态", aggregate.get("constraint_status", "unknown"))

st.subheader("结果型决策摘要")
st.json(summary)
if model_name in {"moving_average", "holt_trend"}:
    st.caption("点预测模型不生成分位数，当前以点预测回填 P50/P90；这不代表已经完成概率校准。")

st.subheader("评估指标")
st.dataframe({"metric": list(metrics.keys()), "value": list(metrics.values())}, use_container_width=True, hide_index=True)

st.subheader("决策记录")
st.dataframe(payload.get("decisions", []), use_container_width=True, hide_index=True)
st.download_button(
    "下载决策 JSON",
    data=json.dumps(payload, ensure_ascii=False, indent=2, default=str),
    file_name=f"decision-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json",
    mime="application/json",
)
