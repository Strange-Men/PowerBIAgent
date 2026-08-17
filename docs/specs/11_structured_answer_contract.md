# 11 — 结构化组合回答契约

> **状态：** M3.0 sales_report contract baseline；M1 生成描述仅作历史兼容
> **目标：** 定义前端组合回答的产品目标与数据契约
> **重要：** 本文档描述未来 M5 前端展示目标。当前 Real API 以 Canonical QueryPlan → QueryResult → VerifiedFactSet → fact-bounded AnswerSpec / ReportSpec 为事实边界

---

## 一、文档目的

定义 PowerBIAgent AI 回答的结构化组合契约。未来一条 AI 回答可以由多个内容块按顺序组成，每个内容块有明确的数据来源和渲染规则。

本文档是前端渲染和 API 设计的权威参考。本文档 **不创建新的 Python 代码或 API**。

## 二、当前已有契约

当前已实现的相关数据契约与 factual artifact：

| 模型 | 职责 |
|------|------|
| `QueryResult` | DAX 查询结果（columns, rows, row_count, source_mode） |
| `VerifiedFactSet` | 对外数字、结果顺序、极值、筛选、时间与 provenance 的唯一事实 authority |
| `AnswerSpec` | 自然语言回答（answer, summary, metrics, evidence） |
| `ReportSpec` | 结构化报表描述（title, template_key, kpis, charts, tables） |
| `RenderedReport` | 报表渲染结果（report_id, template_key, html） |

## 三、当前与未来边界

| 边界 | 说明 |
|------|------|
| **M1.3.2—M1.4** | 历史契约来源；自由 LLM factual generation 已被 ADR-009 supersede |
| **M2.6.4** | Real Answer/Report 只能消费 VerifiedFactSet / QueryResult 可证明事实 |
| **M3.0** | `sales_report` TemplateContract + schema binding + deterministic ReportDataPlan；未实现 Renderer/HTML |
| **M5** | 前端根据本文档实现组合回答渲染 |

**当前不创建**：统一 `AssistantMessageEnvelope`、消息块列表模型、新 API。

## 四、text — 文字内容块

### 产品目标

用于 AI 回答中的自然语言文字。

### 逻辑字段

| 字段 | 类型 | 说明 |
|------|------|------|
| content | string | 自然语言文本（必需） |
| role | string | 固定为 "assistant" |

### 数据来源

`AnswerSpec.answer` — 当前 Real 路径由 deterministic fact-bounded builder 基于 VerifiedFactSet 构造。

### 用途

- 直接回答用户问题
- 给出数据总结
- 说明筛选条件
- 提示空数据
- 提示结果被截断

### 安全约束

- 任何数值、结果顺序、极值、筛选或时间陈述必须由 VerifiedFactSet 证明
- 不允许生成未经验证的严格排名、趋势、因果或外部事实
- 不允许包含可执行代码

## 五、metrics — 指标摘要块

### 产品目标

用于展示少量关键指标（如总计、平均值、增长率），以克制、轻量形式在消息中展示。

### 逻辑字段

| 字段 | 类型 | 说明 |
|------|------|------|
| title | string | 指标组标题（如"关键指标"） |
| items | list | 指标项列表 |
| items[].label | string | 指标名称 |
| items[].value | any | 指标值 |
| items[].format | string | 格式：number / currency / percentage |
| items[].source_field | string | 数据来源字段名 |

### 数据来源

`AnswerSpec.metrics` + `VerifiedFactSet` + `QueryResult`

### 规则

- 数值必须可追溯到 VerifiedFactSet / QueryResult
- 不允许 LLM 自行计算或猜测无法验证的指标
- 不在前端设计成大量彩色 KPI 仪表盘
- 使用克制、轻量形式展示（如文本标签+数值）

### 概念性 JSON 示意

> ⚠️ **未来目标示意，当前未实现，不是现有 API 响应。** 其中“同比增长”不代表 M2 comparison grammar 已支持。

```json
{
  "type": "metrics",
  "title": "关键指标",
  "items": [
    {"label": "总销售额", "value": 12500000, "format": "currency", "source_field": "TotalSales"},
    {"label": "同比增长", "value": 0.083, "format": "percentage", "source_field": "YoYGrowth"}
  ]
}
```

## 六、table — 表格内容块

### 产品目标

用于在 AI 回答中直接展示结构化数据表格。

### 逻辑字段

| 字段 | 类型 | 说明 |
|------|------|------|
| title | string | 表格标题 |
| columns | list[string] | 列名列表 |
| rows | list[list[any]] | 数据行 |
| row_count | int | 实际行数 |
| truncated | bool | 是否被截断 |
| source_mode | string | 数据来源：mock / real |

### 数据来源

`QueryResult`

### 规则

- 表格只能投影 QueryResult 的实际字段与 rows，不得虚构或补算行列
- columns 必须与 QueryResult.columns 一致
- rows 必须与 QueryResult.rows 一致
- truncated 必须与 QueryResult.truncated 一致

### 概念性 JSON 示意

> ⚠️ **目标示意，当前未实现，不是现有 API 响应。**

```json
{
  "type": "table",
  "title": "各区域销售额",
  "columns": ["区域", "销售额(万元)", "增长率"],
  "rows": [
    ["华南", 456, "12.3%"],
    ["华东", 389, "8.1%"],
    ["华北", 312, "-3.2%"]
  ],
  "row_count": 3,
  "truncated": false,
  "source_mode": "mock"
}
```

## 七、chart — 图表内容块

### 产品目标

用于在 AI 回答中直接展示基础图表（柱状图、折线图、饼图、散点图）。

### 逻辑字段

| 字段 | 类型 | 说明 |
|------|------|------|
| type | string | 图表类型：bar / line / pie / scatter |
| title | string | 图表标题 |
| x_field | string | X 轴字段名 |
| y_field | string | Y 轴字段名 |
| series | list[string] | 多系列字段名（可选） |
| data_reference | string | 数据引用（指向 QueryResult.result_id） |
| source_mode | string | 数据来源：mock / real |

### 数据来源

`QueryResult`

### 规则

- type 仅允许 bar / line / pie / scatter
- x_field 和 y_field 必须存在于 QueryResult.columns
- 数据必须引用 QueryResult
- **不允许**让 LLM 生成任意前端代码
- **不允许** HTML、JavaScript 或第三方脚本
- 图表只是结构化描述，由前端安全渲染

### 概念性 JSON 示意

> ⚠️ **目标示意，当前未实现，不是现有 API 响应。**

```json
{
  "type": "chart",
  "type": "bar",
  "title": "各区域销售额对比",
  "x_field": "区域",
  "y_field": "销售额",
  "data_reference": "qr_a1b2c3d4",
  "source_mode": "mock"
}
```

## 八、report_attachment — 报表附件块

### 产品目标

用于在 AI 回答中展示生成的报表附件卡片。

### 逻辑字段

| 字段 | 类型 | 说明 |
|------|------|------|
| report_id | string | 报表唯一 ID |
| title | string | 报表标题 |
| format | string | 文件格式（如 "html"） |
| view_reference | string | 查看报表引用（后端生成） |
| download_reference | string | 下载报表引用（后端生成） |
| source_mode | string | 数据来源：mock / real |

### 数据来源

`RenderedReport` / `ReportSpec`

### 规则

- 不允许 LLM 生成任意外部 URL
- view_reference 和 download_reference 由后端生成
- 格式仅允许后端支持的格式（初始仅 HTML）
- 正式资源接口属于 M3

### 概念性 JSON 示意

> ⚠️ **目标示意，当前未实现，不是现有 API 响应。**

```json
{
  "type": "report_attachment",
  "report_id": "rpt_e5f6g7h8",
  "title": "销售分析报告",
  "format": "html",
  "view_reference": "/api/reports/rpt_e5f6g7h8",
  "download_reference": "/api/reports/rpt_e5f6g7h8/download",
  "source_mode": "mock"
}
```

## 九、数据真实性

### 核心原则

1. 表格数据必须来自 QueryResult
2. 图表数据必须来自 QueryResult
3. 指标与文字 factual claims 必须由 VerifiedFactSet 证明
4. 展示层不得扩大 FactSet / QueryResult 的事实范围
5. 不允许 LLM 虚构行列、数值、排名、趋势、因果或外部事实

### source_mode

`source_mode` 表示数据来源：

| 值 | 含义 |
|----|------|
| `"mock"` | Mock Power BI Adapter 生成的模拟数据 |
| `"real"` | 真实 Power BI MCP 返回的数据 |

**关键规则：** 不能因为使用了真实 DeepSeek Provider 就把 Mock QueryResult 标为 `"real"`。source_mode 反映的是数据层来源，而非 LLM 层来源。

### semantic_model_key

所有数据必须标注其来源语义模型。跨模型数据不得混合在同一回答中（MVP 不支持跨模型查询）。

## 十、VerifiedFactSet / QueryResult 事实来源

`QueryResult` 是表格和图表 rows 的数据来源；`VerifiedFactSet` 是文字、指标、结果顺序、极值、筛选、时间与 provenance 的唯一对外 factual claim authority。

| QueryResult 字段 | 对应内容块 |
|-----------------|-----------|
| columns | table.columns / chart.x_field, chart.y_field |
| rows | table.rows |
| row_count | table.row_count |
| truncated | table.truncated |
| source_mode | table.source_mode / chart.source_mode |
| result_id | chart.data_reference |
| error | 错误处理 |
| execution_time_ms | 可选展示 |

## 十一、AnswerSpec 职责

`AnswerSpec` 负责自然语言层面的回答，但 Real factual content 只能由 fact-bounded builder 从 VerifiedFactSet 构造：

| AnswerSpec 字段 | 对应内容块 |
|----------------|-----------|
| answer | text.content |
| summary | text（摘要变体） |
| metrics | metrics.items |
| evidence | 数据追溯 |
| semantic_model_key | 数据来源标识 |
| source_mode | 数据来源模式 |

## 十二、ReportSpec 职责

`ReportSpec` 负责结构化报表描述；Real KPI、chart fields、table projection 与 insight 必须受 VerifiedFactSet / QueryResult 约束：

| ReportSpec 字段 | 对应内容块 |
|----------------|-----------|
| title | report_attachment.title |
| template_key | 模板标识 |
| kpis | 报表 KPI（非对话指标） |
| charts (ChartSpec) | 报表内图表 |
| tables (TableSpec) | 报表内表格 |
| source_mode | report_attachment.source_mode |

## 十三、RenderedReport 职责

`RenderedReport` 负责报表渲染结果：

| RenderedReport 字段 | 对应内容块 |
|--------------------|-----------|
| report_id | report_attachment.report_id |
| template_key | 模板标识 |
| html | 报表 HTML 内容 |
| source_mode | report_attachment.source_mode |

未来 M3 正式报表资源接口将使用 report_id 提供查看和下载。

## 十四、M1.4 历史实施边界

以下内容记录当时的 M1 实现范围，不是当前 Real authority：

- 真实 DeepSeek Answer 生成（基于 Mock QueryResult）
- 真实 DeepSeek ReportSpec 生成（基于 Mock QueryResult）
- Answer 和 ReportSpec 验证
- 继续使用现有 Python 模型：AnswerSpec、QueryResult、ReportSpec、RenderedReport

M1.4 不完成：

- React 前端
- 统一前端消息 Envelope
- 真实报表下载
- 最近报表
- 最近对话
- 会话搜索
- 多模型切换

## 十五、M1.5/M5 应用层边界

M1.5/M5 可以确定：

- 是否需要统一 `AssistantMessageEnvelope` 包装多个内容块
- 前端如何解析和渲染不同类型的消息块
- 前端如何区分纯文本回答和组合回答

## 十六、M3 报表资源边界

M3.0 已确定：

- 唯一 production template 为 `sales_report`
- TemplateContract 固定四查询及来源/筛选/时间/生成时间 metadata
- schema/model fingerprint mismatch 或必需对象缺失时 fail closed
- ReportDataPlan 不读取 LLM draft，每个 sub-query 复用 M2 封板执行与事实链

M3.1/3.2 后续可以实现：

- deterministic Report Data Contract / ReportSpec 与 Fixed Renderer
- 报表资源 ID 生成和管理
- 查看报表接口
- 下载 HTML 接口
- 最近报表所需后端资源边界

## 十七、M5 前端渲染边界

M5 将完成：

- 根据本文档契约渲染组合回答
- 表格渲染（浅灰分隔线、舒适行距、数字对齐）
- 图表渲染（bar/line/pie/scatter，单一蓝色，结构化字段驱动）
- 报表附件卡片渲染
- 输入器和"+"菜单
- 左侧栏和欢迎态
- 响应式适配

## 十八、安全限制

### 绝对禁止

1. LLM 生成任意 HTML 代码
2. LLM 生成任意 JavaScript 代码
3. LLM 生成第三方脚本引用
4. LLM 生成任意外部 URL
5. 图表使用 LLM 生成的代码（须用结构化字段）
6. LLM 虚构数据（必须引用 QueryResult）
7. LLM 生成前端可执行代码

### 必须校验

1. 表格字段与 QueryResult.columns 一致
2. 图表字段与 QueryResult.columns 一致
3. 指标值与文字事实可追溯到 VerifiedFactSet / QueryResult
4. source_mode 与数据层一致
5. 报表引用由后端生成
6. 模型权限和模板权限

### DeepSeek 是模型能力

DeepSeek 提供语言模型能力，不是数据来源。M1 的 QueryPlan/DAX/Answer/ReportSpec 生成描述是历史兼容契约；当前 Real 路径只保留 Intent/语言草稿/受限候选选择，DAX 与 factual Answer/Report 由 ADR-009 的确定性 Builder/VerifiedFactSet 控制。source_mode 不能因为使用真实 DeepSeek 而被标记为 real。

---

*最后更新：2026-08-17 | M3.0 sales_report contract boundary*
