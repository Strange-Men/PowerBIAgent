# 11 — 结构化组合回答契约

> **状态：** M5.3 presentation contract 已实现；M5.3.1 已收紧为只投影 VerifiedFactSet 数据事实覆盖字段。
> **边界：** 本契约只增加安全展示层，不改变 WorkMemory、QueryResult、VerifiedFactSet、ReportSpec 或 ReportArtifact 的事实权威。

## 一、目标

一条 Assistant 消息可以按后端实际产物动态包含：

- `text`
- `metric`
- `table`
- `chart`
- `report_attachment`

所有内容块都是可选的，不规定固定顺序，也不要求每轮出现指标、表格或图表。clarification、unsupported、error 和 empty 继续使用自然语言终态，不补空表或假图。

## 二、事实来源

| 展示内容 | 唯一允许来源 |
|---|---|
| 文字回答 | 受事实约束的 terminal answer / clarification / unsupported reason |
| 指标 | `VerifiedFactSet` 证明且可回指 `QueryResult` 的 scalar fact |
| 表格 | VerifiedFactSet 数据事实 `source_fields` 覆盖的 QueryResult 列与对应 rows 投影 |
| 柱状图/折线图 | 同一 verified presentation dataset 的字段引用 |
| 报表附件 | `ReportArtifact` canonical `report_id` 与资源 API |

禁止从 answer 文字反解析数字，禁止从 `execution_audit` 拼 rows，禁止由 LLM 或前端生成第二份 Chart data，禁止为视觉完整度补假数据。

## 三、`PresentationEnvelope`

`ChatResponse.presentation` 与 History item 的 `presentation` 使用同一只读结构：

```json
{
  "version": 1,
  "datasets": [
    {
      "result_id": "result-...",
      "verified_fact_set_id": "fact-set-...",
      "semantic_model_key": "local_desktop_model",
      "source_mode": "real",
      "columns": ["Category", "Total Sales"],
      "rows": [["A", 120], ["B", 80]],
      "row_count": 2,
      "truncated": false
    }
  ],
  "blocks": [
    {"type": "text", "content": "..."},
    {"type": "table", "data_reference": "result-...", "title": "查询结果"},
    {
      "type": "chart",
      "data_reference": "result-...",
      "visual_type": "bar",
      "title": "对比",
      "x_field": "Category",
      "y_field": "Total Sales"
    }
  ]
}
```

示例只说明 shape；值必须来自当前请求真实 QueryResult，不能复制为 fixture 或前端常量。

### 3.1 dataset

一个 QueryResult 在 envelope 中最多对应一份 dataset。字段含义：

| 字段 | 规则 |
|---|---|
| `result_id` | block 的唯一 `data_reference` |
| `verified_fact_set_id` | 证明 dataset 已经过 VerifiedFactSet 边界 |
| `semantic_model_key` / `source_mode` | 必须与 QueryResult 和 FactSet 一致 |
| `columns` | 唯一列名；只包含 scalar/grouped/ranking/min/max 数据事实 `source_fields` 覆盖字段，并保持其在 QueryResult 中的原顺序 |
| `rows` | 对 QueryResult rows 做相同列投影；每行长度必须等于 columns 长度 |
| `row_count` | 必须等于 rows 实际数量 |
| `truncated` | 原样保留 QueryResult 截断状态 |

builder 仍要求 FactSet 的完整 `result_columns` 与 QueryResult 一致，用作 authority coherence witness；presentation dataset 只暴露数据型 VerifiedFact 的 `source_fields`。QueryResult error、result/fact ID、model、source、columns、row shape、row count 或 truncated 不一致时 fail closed，不返回部分 presentation。

### 3.2 block 引用

- `metric`：引用 `data_reference`、`value_field` 与 `row_index`；不得内嵌第二份 value。
- `table`：只引用 dataset；表头和 rows 直接读取 dataset。
- `chart`：只引用 dataset、`x_field`、`y_field` 与允许的 `visual_type`。
- `report_attachment`：只携带 canonical `report_id`，查看/下载 URL 仍由受控资源 API 生成。
- 所有引用字段、row index 和 dataset 必须在 envelope validation 时存在；dangling reference 受控失败。

## 四、确定性投影规则

`StructuredPresentationBuilder` 只消费已经产生的 `CanonicalQueryPlan`、`QueryResult` 与 `VerifiedFactSet`：

1. 总是可以加入真实 terminal text。
2. scalar fact 产生 `metric` 引用。
3. grouped fact 且有 rows 时产生 `table`。
4. grouped result 至少两行、Y 字段全部为数值时才产生 chart。
5. 时间维度或真实日期值产生 `line`；其他 grouped comparison 产生 `bar`。
6. report 成功时产生 text + `report_attachment`，不把 ReportSpec 数据复制进 chat dataset。
7. QueryResult 意外增加但未被数据型 VerifiedFact `source_fields` 覆盖的列时，该列及对应 cell 不进入 dataset。

前端不重新判断业务意图，不把普通表格升级成趋势，不修改数据顺序，不计算新指标。

## 五、动态渲染

| 场景 | 可能展示 |
|---|---|
| 普通问答 | text |
| 单值问答 | text + metric |
| 分组比较 | text + table；数据满足条件时加 bar |
| 时间趋势 | text + table；数据满足条件时加 line |
| 报表生成 | text + report attachment |
| clarification / unsupported / error / empty | 仅自然语言提示 |

前端按 blocks 实际顺序渲染；没有 block 时才使用既有 terminal-state 文字 fallback。不得强制任何块出现。

## 六、History 与 presentation transcript

terminal Snapshot 可以持久化：

- `user_message`
- `presentation`

History API 返回保存的 user message、assistant terminal result 和同一 presentation envelope，前端按轮次恢复完整可理解对话。它们都是 presentation metadata：

- 不输入 Grounding/StateTransition；
- 不参与 Canonical QueryPlan；
- 不提交或恢复 WorkMemory；
- 不覆盖 QueryResult/VerifiedFactSet；
- 不成为 report factual authority。

旧 Snapshot 没有 `user_message` 时只显示仓库中真实存在的旧结果；仅对明确的 legacy `analysis_goal="用户提问: ..."` 做精确兼容，不臆造逐字 transcript。

## 七、前端渲染约束

### 指标

- 使用 dataset 的原值进行 locale-safe 展示；不改精度或业务单位。
- 缺字段或 row 时不渲染。

### 表格

- columns/rows 原顺序展示。
- 容器允许键盘聚焦和横向滚动。
- 不增加前端排序、筛选、分页事实工作台。

### 图表

- 当前只支持简单 `bar` 与 `line`。
- 尺寸随容器响应式变化；数值/标签仍取 dataset。
- 不支持 3D、自由 ChartSpec、前端聚合或插值。

### 报表附件

- 只有 canonical `report_id` 存在时展示。
- 查看和下载继续调用同一 report resource；不把 HTML 放入 Snapshot 或 presentation。

## 八、安全与测试要求

必须直接覆盖：

- scalar → metric；
- grouped → table + bar；
- time series → table + line；
- QueryResult/FactSet 不一致 fail closed；
- unexpected QueryResult field 不进入 presentation；
- dangling dataset/field/row reference fail closed；
- report attachment 只引用 report_id；
- History serialization/restart 后 presentation shape 保持一致；
- 前端不从 answer/audit 构造事实。

自动化测试使用临时 SQLite/report root 与唯一 `m53-test-*` 前缀，并在 fixture/finally 中精确清理；不得清空用户 `local_state`。

---

*创建日期：2026-08-03 | M1.3.2 前端视觉与结构化回答契约固化*
*最后更新：2026-08-23 | M5.3.1 verified-field projection final hardening*
