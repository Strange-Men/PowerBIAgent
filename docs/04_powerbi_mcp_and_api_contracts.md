# 04 — Power BI MCP 与 API 契约

> **状态：** M1.3.2 核对并更新
> **关联 ADR：** ADR-003
> **API 源码：** `backend/app/api/routes.py`、`backend/app/main.py`
> **数据契约源码：** `backend/app/schemas/data_contracts.py`

---

## 一、当前 API 路由（以实际代码为准）

### 已实现

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| `GET` | `/health` | 健康检查（Mock 200 / DeepSeek 503） | ✅ M0.4 |
| `POST` | `/api/v1/chat` | 非流式对话接口（当前仅 Mock 可用） | ✅ M0.4 |

### 计划中的接口（PRD 定义，尚未实现）

| 方法 | 路径 | 说明 | 目标轮次 |
|------|------|------|---------|
| `GET` | `/api/semantic-models` | 返回可选 Power BI 语义模型列表 | M2+ |
| `GET` | `/api/report-templates` | 返回可选固定报表模板列表 | M3+ |
| `GET` | `/api/reports/{report_id}` | 预览或下载已生成报表 | M3+ |

> **注意：** PRD 中列出的 `/api/semantic-models`、`/api/report-templates`、`/api/reports/{report_id}` 为计划接口，当前未实现。不得在文档中将其描述为已有接口。

---

## 一、PowerBIAdapter 设计

### 1.1 接口（`backend/app/powerbi/base.py`）

| 方法 | 说明 |
|------|------|
| `health_check()` | 连接健康检查 |
| `get_semantic_model_schema(key)` | 获取语义模型结构 |
| `execute_dax(DAXRequest)` | 执行 DAX 查询 |
| `normalize_result(raw)` | 标准化原始响应 |
| `normalize_error(raw)` | 标准化原始错误 |

### 1.2 MockPowerBIAdapter（`backend/app/powerbi/mock.py`）

- 从 `harness/fixtures/` 加载 Mock Schema 和 QueryResult
- 不依赖网络和 Microsoft 账号
- 严格匹配 scenario_key，未知场景明确失败
- 支持模拟：正常数据、空数据、超时、无权限、DAX 错误、超大结果

### 1.3 RemoteMCPPowerBIAdapter（`backend/app/powerbi/remote_mcp.py`）

- M0.3 仅骨架，所有真实调用标记 `NotImplementedError("TODO: M2")`
- 配置边界完整：Server URL、Tenant ID、Client ID、超时、重试

## 二、OAuth 认证风险（ADR-003）

### 关键发现

1. **VS Code 能访问 ≠ 自定义客户端能访问** — VS Code 有微软预注册的 Client ID
2. **必须手动注册 Entra Application** — 需要 Azure 管理员权限
3. **需要 Power BI 管理员启用 Tenant 设置**
4. **早期 2026 年有 Remote MCP 端点中断报告**

### 授权流程

- M2: MSAL device code flow + 本地 token 缓存
- Token 获取、刷新和存储由 Adapter 内部管理
- 不暴露 Token 到 Agent 或业务层

## 三、核心数据契约（`backend/app/schemas/data_contracts.py`）

### 3.1 契约职责总览

| 模型 | 职责 | 数据来源 |
|------|------|---------|
| **QueryResult** | 表格和图表数据的事实来源。包含 columns、rows、row_count、source_mode 等。内置一致性校验（row_count vs rows 长度、每行字段 vs columns 数量） | Power BI MCP（当前 Mock） |
| **AnswerSpec** | 自然语言答案、摘要、指标和证据。负责直接回答用户问题、给出总结、说明筛选条件。answer 字段为必填核心文本 | LLM 基于 QueryResult 生成 |
| **ReportSpec** | 结构化报表描述。包含 title、template_key、kpis (KPISpec)、charts (ChartSpec)、tables (TableSpec)、insights 等。禁止任意 HTML/JS/外部脚本 | LLM 基于 QueryResult 和模板生成 |
| **RenderedReport** | 报表渲染结果。包含 report_id、template_key、html 等。未来提供报表资源查看和下载引用 | Report Renderer 基于 ReportSpec 渲染 |

### 3.2 QueryPlan
normalized_question, semantic_model_key, measures, dimensions, filters (StructuredFilter), time_range, sort, top_n, comparison_mode, requested_template, inherited_context, is_mock

### 3.3 DAXRequest
semantic_model_key, dax, max_rows, timeout_seconds, request_id, is_mock

### 3.4 QueryResult — 数据事实来源
result_id, semantic_model_key, columns, rows, row_count, execution_time_ms, source_mode, request_id, error (PowerBIError), truncated

内置一致性校验：row_count vs rows 长度、每行字段 vs columns 数量。

**关键规则：**
- 表格和图表数据必须来自 QueryResult
- LLM 只负责解释或选择展示范围，不得虚构行列
- source_mode 表示数据来源，不能因为使用真实 DeepSeek 就把 Mock QueryResult 标为 real

### 3.5 AnswerSpec — 自然语言回答
answer, summary, metrics, evidence, filters, semantic_model_key, source_mode, generated_at

**关键规则：**
- answer 字段为自然语言结论，由 LLM 基于 QueryResult 生成
- metrics 展示少量关键指标，数值必须来自 QueryResult
- AnswerSpec 负责文字结论、摘要和指标，不承载完整表格数据
- 表格数据直接来自 QueryResult，图表的数据事实来源也是 QueryResult
- 不允许 LLM 自行计算无法验证的指标
- evidence 提供数据来源追溯
- source_mode 与 QueryResult.source_mode 应一致

### 3.6 ReportSpec — 结构化报表
title, template_key, summary, kpis (KPISpec), charts (ChartSpec), tables (TableSpec), insights, data_source, filters, generated_at, source_mode

禁止任意 HTML、JavaScript、外部脚本、未登记模板、不存在字段。

### 3.7 UserContext
user_id, roles, allowed_semantic_models, allowed_templates, allowed_tools

---

## 三-A、前端组合回答目标（未来 M5，当前不实现）

> **本节描述未来前端组合回答的产品目标，不代表当前 API 已经支持。**

### 目标形态

一条 AI 回答可由多个内容块按顺序组成，内容类型至少包括：

| 类型 | 说明 | 数据来源 |
|------|------|---------|
| `text` | 自然语言结论、总结、筛选说明、空数据提示、截断提示 | AnswerSpec.answer |
| `metrics` | 少量关键指标（数值来自 QueryResult，不允许 LLM 虚构） | QueryResult / AnswerSpec.metrics |
| `table` | title、columns、rows、row_count、truncated、source_mode | QueryResult |
| `chart` | type (bar/line/pie/scatter)、title、x_field、y_field、series、data_reference | QueryResult |
| `report_attachment` | report_id、title、format、view_reference、download_reference、source_mode | RenderedReport |

### 安全限制

- 图表字段必须存在于 QueryResult.columns
- 图表数据必须引用 QueryResult，不允许 LLM 虚构
- 图表使用结构化字段描述，**禁止** LLM 生成 HTML、JavaScript、第三方脚本或任意前端代码
- 报表查看和下载引用由后端生成，**禁止** LLM 生成任意外部 URL
- source_mode 表示数据来源，不能因使用真实 DeepSeek 而将 Mock QueryResult 标为 real
- LLM 不得生成任意外部 URL 或可执行脚本

### 当前与未来边界

| 能力 | 当前状态 | 目标轮次 |
|------|---------|---------|
| 统一前端消息 Envelope | ❌ 不存在 | M1.5/M5 确定 |
| AnswerSpec + QueryResult | ✅ 已实现 | — |
| ReportSpec + RenderedReport | ✅ Mock 可运行 | M3 正式渲染 |
| 表格展示 | ✅ AnswerSpec 可携带 | M5 前端渲染 |
| 图表展示 | ❌ 当前无 | M5 前端渲染 |
| 报表查看/下载 | ❌ 当前无 | M3 报表资源 |
| LLM 生成 HTML/JS | ❌ 永久禁止 | — |

## 四、只读 DAX 安全

- 仅允许：EVALUATE、DEFINE + EVALUATE
- 禁止：SQL、写操作、跨模型引用、Python/Shell/PowerShell/JavaScript
- 安全边界来自：ToolGateway、ValidationService、semantic_model_key 白名单、Schema 字段验证、最大行数、超时、最大重试

## 五、M0.3/M2/M3 边界

| 项目 | M0.3 | M2 | M3 |
|------|------|----|----|
| PowerBIAdapter 接口 | ✅ | — | — |
| MockPowerBIAdapter | ✅ 可运行 | — | — |
| Remote Adapter | ✅ 骨架 | ✅ 真实连接 | — |
| API 数据契约 | ✅ 全部 Pydantic | — | — |
| OAuth/Token | ✅ 设计文档 | ✅ 实现 | — |
| 真实 DAX 查询 | ❌ | ✅ | — |
| ReportSpec Schema | ✅ 完整 | — | — |
| 生产报表模板/HTML | ❌ | ❌ | ✅ |

---

*最后更新：2026-08-03 | M1.3.2 前端视觉与结构化回答契约固化*
