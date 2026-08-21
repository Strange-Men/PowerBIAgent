# 11 — 结构化组合回答契约

> **状态：** M5.1 — React 前端实现与核心联调（已完成）。动态回答原则已实现。
> **目标：** 定义前端组合回答的产品目标与数据契约
> **重要：** 本文档描述前端渲染规则。当前 Real API 以 ChatResponse（含 answer/report/clarification/unsupported 字段 + QueryResult 审计元数据）为数据来源。内容块类型是前端根据后端产物动态渲染的产物类型，不等同于中间数据模型。

---

## 一、文档目的

定义 PowerBIAgent AI 回答的结构化组合契约。一条 AI 回答可以由多个内容块按需组合，每个内容块有明确的数据来源和渲染规则。

## 二、动态回答渲染原则（核心）

前端**不得**将 AI 回答固定为”文字 → 指标 → 表格 → 图表 → 报表附件”这类每次必现的序列。

前端根据当前 Turn 的用户意图和后端实际返回产物**动态渲染**。内容块类型只是渲染的产物分类，不是后端 API 的数据结构。

| 场景 | 可能渲染的内容 |
|------|--------------|
| 普通问答 | 仅有文字 |
| 数据查询 | 文字 + 表格（数据来自后端 QueryResult） |
| 简单数字追问 | 仅有文字或指标 |
| 多轮追问 | 仅更新文字/表格 |
| 比较/趋势且后端提供可视化数据 | 才显示图表 |
| 用户要求生成报表且后端生成 ReportArtifact | 才显示 HTML 报表附件卡片 |
| clarification | 文字（来自 ChatResponse.clarification_question） |
| unsupported | 文字（来自 ChatResponse.unsupported_reason） |
| error | 文字（来自 ChatResponse.error_type + answer） |
| empty | 文字说明，不生成假表格/假图表 |

## 三、当前与未来边界

| 边界 | 说明 |
|------|------|
| **M1.3.2—M1.4** | 历史契约来源；自由 LLM factual generation 已被 ADR-009 supersede |
| **M2.6.4** | Real Answer/Report 只能消费 VerifiedFactSet / QueryResult 可证明事实 |
| **M3.0** | `sales_report` TemplateContract + schema binding + deterministic ReportDataPlan |
| **M3.1** | deterministic `ReportSpec` → static HTML → `ReportArtifact` / view / download |
| **M3.2** | CSS bars + responsive/static safety hardened acceptance |
| **M5.0** | 文档契约固化、动态回答原则确认、UI↔后端能力映射；不写 React |
| **M5.1** | ✅ 前端已动态渲染现有 ChatResponse terminal state 与 ReportArtifact；结构化 rows/ChartSpec 缺口保持 fail-closed |
| **M5.2** | 视觉与交互收口 |

**M5.1 决策：** 不创建新的后端统一 `AssistantMessageEnvelope` 或新 API。前端 typed adapter 直接消费现有 ChatResponse/History schema。

## 四、text — 文字内容块

### 产品目标

用于 AI 回答中的自然语言文字。

### 逻辑字段

| 字段 | 类型 | 说明 |
|------|------|------|
| content | string | 自然语言文本（必需） |
| role | string | 固定为 “assistant” |

### 数据来源

ChatResponse 的相关字段：

| 场景 | 来源字段 |
|------|---------|
| 正常数据回答 | `answer` |
| clarification | `clarification_question` |
| unsupported | `unsupported_reason` |
| error | `answer`（已有内容）+ `error_type`（用于分类展示） |

### 用途

- 直接回答用户问题
- 给出数据总结
- 说明筛选条件
- 提示空数据
- 提示结果被截断
- clarification 追问
- unsupported 原因
- error 提示

### 安全约束

- 任何数值、结果顺序、极值、筛选或时间陈述必须由 VerifiedFactSet 证明
- 不允许生成未经验证的严格排名、趋势、因果或外部事实
- 不允许包含可执行代码

## 五、metrics — 指标摘要块

### 产品目标

用于展示少量关键指标（如总计、平均值），以克制、轻量形式在消息中展示。

### 数据来源

后端 QueryResult / VerifiedFactSet。当前 ChatResponse 不直接暴露独立 metrics 结构；`usage` 不是事实数据，`execution_audit` 也不提供可展示指标结构。M5.1 不从 answer/audit 反解析指标，因此只展示 fact-bounded answer 文字。

### 规则

- 数值必须可追溯到 VerifiedFactSet / QueryResult
- 不允许 LLM 自行计算或猜测无法验证的指标
- 不在前端设计成大量彩色 KPI 仪表盘
- 使用克制、轻量形式展示（如文本标签+数值）
- 无可展示指标时不生成空指标块

## 六、table — 表格内容块

### 产品目标

用于在 AI 回答中直接展示结构化数据表格。

### 数据来源

后端 QueryResult。当前 ChatResponse 与 History 不暴露 QueryResult columns/rows，现有 `execution_audit` 只有审计元数据。M5.1 将其记录为最小契约缺口，未修改 M4 Snapshot/Persistence，也不生成空表格或假 rows。

### 前端渲染约束

- columns 必须与后端 QueryResult.columns 一致
- rows 必须与后端 QueryResult.rows 一致
- `truncated` 标志影响表格底部提示
- 没有表格数据时不生成空表格

### 概念性 JSON 示意

> ⚠️ **目标示意，当前未实现统一 envelope，不是现有 API 响应。**

```json
{
  “type”: “table”,
  “title”: “各区域销售额”,
  “columns”: [“区域”, “销售额(万元)”],
  “rows”: [
    [“华南”, 456],
    [“华东”, 389]
  ],
  “row_count”: 2,
  “truncated”: false,
  “source_mode”: “mock”
}
```

## 七、chart — 图表内容块

### 产品目标

用于在 AI 回答中直接展示基础图表（柱状图、折线图、环形图）。

### 数据来源

后端 QueryResult，仅在后端提供可视化数据且是 comparison/trend 场景时渲染。

### 前端渲染约束

- type 仅允许后端支持的类型（bar/line/donut）
- 字段必须存在于后端 QueryResult.columns
- 数据必须引用后端数据
- **不允许**让 LLM 生成任意前端代码
- **不允许** HTML、JavaScript 或第三方脚本
- 无可视化数据时不生成图表

### 概念性 JSON 示意

> ⚠️ **目标示意，当前未实现统一 envelope，不是现有 API 响应。**

```json
{
  “type”: “chart”,
  “visual_type”: “bar”,
  “title”: “各区域销售额对比”,
  “x_field”: “区域”,
  “y_field”: “销售额”,
  “data_reference”: “qr_a1b2c3d4”,
  “source_mode”: “mock”
}
```

## 八、report_attachment — 报表附件块

### 产品目标

用于在 AI 回答中展示生成的报表附件卡片。

### 数据来源

ChatResponse.report 字段（`ReportResponse` 对象，包含 report_id、template_key、view_reference、download_reference、content_hash 等）。

### 展示条件

仅当 ChatResponse.report 存在（非 null）且包含有效 report_id 时显示。

### 前端渲染约束

- report_id 来自后端
- view_reference 和 download_reference 由后端生成
- 格式仅允许后端支持的格式（初始仅 HTML）
- **禁止** LLM 生成任意外部 URL
- 后端无报表时不生成报表附件卡片

## 九、前端实时渲染流程（概念）

```
ChatResponse 到达
→ 解析 response_type / terminal_state
→ 根据以下规则决定渲染内容：

response_type=”answer” + answer 有内容
  → 渲染文字 (text)
  → 如后端有 QueryResult 数据行 → 渲染表格 (table)
  → 如后端有可视化数据 → 渲染图表 (chart)
  → 如 report 字段存在 → 渲染报表附件 (report_attachment)

response_type=”clarification” + clarification_question 有内容
  → 渲染文字 (clarification_question)

response_type=”unsupported” + unsupported_reason 有内容
  → 渲染文字 (unsupported_reason)

response_type=”error” 或 terminal_state=”error”
  → 渲染文字 (answer 或 error 摘要)

terminal_state=”completed” + answer 为空
  → 渲染 “暂无数据” 文字提示
```

> 以上是前端渲染逻辑概念，不创建新的后端 API 或中间数据结构。

## 十、数据真实性

### 核心原则

1. 表格数据必须来自后端 QueryResult
2. 图表数据必须来自后端 QueryResult
3. 指标与文字 factual claims 必须由 VerifiedFactSet 证明
4. 展示层不得扩大 FactSet / QueryResult 的事实范围
5. 不允许 LLM 虚构行列、数值、排名、趋势、因果或外部事实
6. 前端不得为了页面完整度创造 KPI、表格、图表、趋势或事实结论

### source_mode

`source_mode` 表示数据来源：

| 值 | 含义 |
|----|------|
| `”mock”` | Mock Power BI Adapter 生成的模拟数据 |
| `”real”` | 真实 Power BI MCP 返回的数据 |

**关键规则：** 不能因为使用了真实 DeepSeek Provider 就把 Mock QueryResult 标为 `”real”`。source_mode 反映的是数据层来源，而非 LLM 层来源。

### semantic_model_key

所有数据必须标注其来源语义模型。跨模型数据不得混合在同一回答中（MVP 不支持跨模型查询）。

## 十一、当前已有后端数据模型

当前已实现的相关数据契约与 factual artifact——这些是**后端数据模型**，不是前端 API 响应结构。前端通过 ChatResponse 获取展示所需信息。

| 模型 | 职责 |
|------|------|
| `QueryResult` | DAX 查询结果（columns, rows, row_count, source_mode） |
| `VerifiedFactSet` | 对外数字、结果顺序、极值、筛选、时间与 provenance 的唯一事实 authority |
| `AnswerSpec` | 自然语言回答（answer, summary, metrics, evidence） |
| `ReportSpec` | 结构化报表描述（title, template_key, kpis, charts, tables） |
| `SalesReportData` | 查询结果/事实集的确定性销售报表中间产物 |
| `ReportArtifact` | repository 管理的 HTML artifact、provenance、hash 与 view/download reference |

## 十二、ChatResponse 与内容块映射

ChatResponse 是前端主要数据来源：

| ChatResponse 字段 | 对应内容块 | 说明 |
|------------------|-----------|------|
| `answer` | text | 主要文字内容 |
| `clarification_question` | text | clarification 场景的文字 |
| `unsupported_reason` | text | unsupported 场景的文字 |
| `report` | report_attachment | 报表附件卡片数据 |
| `response_type` | 渲染决策 | answer/clarification/unsupported/error 决定渲染分支 |
| `terminal_state` | 渲染决策 | completed / clarification / unsupported / error |
| `execution_audit` | 可选调试信息 | 包含 query_result 等审计元数据，前端可提取表格数据 |
| `source_mode` | 内容块属性 | “mock” / “real” |
| `is_mock` | 内容块属性 | Mock LLM 时为 True |

## 十三、VerifiedFactSet / QueryResult 事实来源

`QueryResult` 是表格和图表 rows 的数据来源；`VerifiedFactSet` 是文字、指标、结果顺序、极值、筛选、时间与 provenance 的唯一对外 factual claim authority。

## 十四、ReportSpec 职责

`ReportSpec` 负责结构化报表描述；Real KPI、chart fields、table projection 与 insight 必须受 VerifiedFactSet / QueryResult 约束。

## 十五、ReportArtifact 职责

M3.1 的 `ReportArtifact` 负责后端管理的报表资源。正式资源接口使用 report_id 提供查看和下载；不接受客户端文件路径或外部 URL。

## 十六、ChatResponse 字段说明

ChatResponse 是前端渲染 AI 回答的主要数据结构（见 `backend/app/api/schemas.py`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| request_id | str | 请求 ID |
| conversation_id | str | 会话 ID |
| terminal_state | str | terminal state: completed / clarification / unsupported / error |
| intent | str | 意图分类 |
| response_type | str | 响应类型 |
| answer | str? | 数据问答场景的文字回答 |
| report | ReportResponse? | 报表场景的报表数据（report_id/view/download reference） |
| clarification_question | str? | clarification 场景的追问 |
| unsupported_reason | str? | unsupported 场景的拒绝原因 |
| error_type | str? | 错误类型代码 |
| is_mock | bool | LLM 是否为 Mock |
| idempotent_replay | bool | 是否为幂等重放 |
| source_mode | str | 数据来源（mock / real） |

## 十七、安全限制

### 绝对禁止

1. LLM 生成任意 HTML 代码
2. LLM 生成任意 JavaScript 代码
3. LLM 生成第三方脚本引用
4. LLM 生成任意外部 URL
5. 图表使用 LLM 生成的代码（须从后端获取数据）
6. LLM 虚构数据（必须引用后端 QueryResult）
7. LLM 生成前端可执行代码
8. 前端渲染固定内容序列（每次 AI 回答都相同结构）

### 必须校验

1. 表格字段与后端 columns 一致
2. 图表字段与后端 columns 一致
3. 指标值与文字事实可追溯到 VerifiedFactSet / QueryResult
4. source_mode 与数据层一致
5. 报表引用由后端生成
6. 无可展示数据时不生成假空内容块

### DeepSeek 是模型能力

DeepSeek 提供语言模型能力，不是数据来源。source_mode 不能因为使用真实 DeepSeek 而被标记为 real。

---

*创建日期：2026-08-03 | M1.3.2 前端视觉与结构化回答契约固化*
*最后更新：2026-08-21 | M5.1 动态回答实现与结构化数据契约缺口确认*
