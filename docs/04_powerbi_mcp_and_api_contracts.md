# 04 — Power BI MCP 与 API 契约

> **状态：** M2.6.4 路径校准；早期 Remote/LLM DAX 描述以 ADR-006—ADR-009 为准
> **关联 ADR：** ADR-003（partially superseded）、ADR-005—ADR-009
> **API 源码：** `backend/app/api/routes.py`、`backend/app/main.py`
> **数据契约源码：** `backend/app/schemas/data_contracts.py`

---

## 一、当前 API 路由（以实际代码为准）

### 已实现

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| `GET` | `/health` | 当前运行模式配置就绪检查；不调用 LLM、不启动 MCP、不探测 Desktop 在线状态 | ✅ Mock / DeepSeek+Mock / DeepSeek+Local 配置 |
| `POST` | `/api/v1/chat` | 非流式对话接口；Mock+Mock、DeepSeek+Mock、DeepSeek+Local MCP 共用 TurnPipeline | ✅ Real M2 链已验证 |
| `GET` | `/api/reports/{report_id}` | 查看 repository-owned static HTML | ✅ M3/M4 |
| `GET` | `/api/reports/{report_id}/download` | 下载 UTF-8 HTML | ✅ M3/M4 |
| `GET` | `/api/v1/conversations`、`/search`、`/{id}/history`、`/{id}/reports` | namespace-first recent/search/structured history/report history | ✅ M4.3/M4.4；SQLite-only |
| `POST/DELETE` | `/api/v1/conversations/{id}/archive`、`/api/v1/conversations/{id}` | 同 namespace 归档/删除 | ✅ M4.3/M4.4 |
| `GET` | `/api/v1/semantic-models` | 经只读 ToolGateway → PowerBIAdapter → Local MCP 发现当前可连接 Desktop 模型；返回 safe catalog 与 runtime namespace | ✅ M5.2 最小只读 endpoint |

### 计划中的接口（PRD 定义，尚未实现）

| 方法 | 路径 | 说明 | 目标轮次 |
|------|------|------|---------|
| `GET` | `/api/report-templates` | 返回可选固定报表模板列表 | M3+ |

> **注意：** `/api/v1/semantic-models` 只返回 backend-owned stable key、display name、source/type、availability/connected 和 runtime namespace；不返回端口、connection string、process/file path、MCP raw payload 或 schema 业务 metadata。`/api/report-templates` 仍未实现，当前前端只维护 registry-owned `sales_report` catalog。

---

## 二、PowerBIAdapter 设计

### 2.1 接口（`backend/app/powerbi/base.py`）

| 方法 | 说明 |
|------|------|
| `health_check()` | 连接健康检查 |
| `get_semantic_model_schema(key)` | 获取语义模型结构 |
| `execute_dax(DAXRequest)` | 执行 DAX 查询 |
| `normalize_result(raw)` | 标准化原始响应 |
| `normalize_error(raw)` | 标准化原始错误 |

### 2.2 MockPowerBIAdapter（`backend/app/powerbi/mock.py`）

- 从 `harness/fixtures/` 加载 Mock Schema 和 QueryResult
- 不依赖网络和 Microsoft 账号
- 严格匹配 scenario_key，未知场景明确失败
- 支持模拟：正常数据、空数据、超时、无权限、DAX 错误、超大结果

### 2.3 RemoteMCPPowerBIAdapter（`backend/app/powerbi/remote_mcp.py`）

- Deferred production skeleton；当前不作为 M2 Real 主路径，真实调用仍明确 `NotImplementedError`
- 配置边界完整：Server URL、Tenant ID、Client ID、超时、重试

### 2.4 LocalMCPPowerBIAdapter（`backend/app/powerbi/local_mcp.py`）

- 当前 M2 Real Provider：只读 stdio Local MCP + Power BI Desktop
- 只负责 Provider / protocol Adapter；上层仍是 TurnPipeline → ToolGateway → PowerBIAdapter 的唯一控制面
- 已真实验证 schema、DAX、QueryResult、production Chat 与 committed Memory；Real 失败不回退 Mock
- M5.2 Real conversation/history/report 启动必须显式使用 `LLM_MODE=deepseek`、`POWERBI_MODE=local_mcp`、`PERSISTENCE_BACKEND=sqlite`；完整 `sales_report` 的 schema + 4 DAX + render 需要 `MAX_TOOL_CALLS=8`，更低预算按控制面规则 fail closed
- Remote MCP 只有外部管理员/授权条件具备且用户重新批准后才恢复开发

### 2.5 M5.2 Desktop 模型 discovery

- 浏览器不能读取 `.pbix`；模型发现只能由后端通过 `connection_operations/ListLocalInstances`、只读连接验证和 Adapter 安全映射完成
- API 不直接调用 MCP；调用路径固定为 API → SemanticModelDiscoveryService → read-only ToolGateway → PowerBIAdapter → Local MCP
- 当前 Local 执行合同一次只选择一个可稳定连接的 Desktop 模型，因此 catalog 只暴露“当前已连接模型”；不把同一内部 key 伪装成多个可选 PBIX
- M2 封板兼容 key 可以继续作为后端内部执行 identity，但前端不得硬编码或用固定“销售数据”别名冒充 discovery
- 无 Desktop/无可连接模型时返回空 items 和安全状态；不回退 Mock、不返回连接细节

## 三、OAuth 认证风险（ADR-003/ADR-006，Remote Deferred）

### 关键发现

1. **VS Code 能访问 ≠ 自定义客户端能访问** — VS Code 有微软预注册的 Client ID
2. **必须手动注册 Entra Application** — 需要 Azure 管理员权限
3. **需要 Power BI 管理员启用 Tenant 设置**
4. **早期 2026 年有 Remote MCP 端点中断报告**

### 未来 Remote 授权流程

- 仅在重新批准的 Remote production stage 按 ADR-006 实现；不属于当前 M2 Local 链
- Token 获取、刷新和存储必须隔离在 Adapter 边界内
- 不暴露 Token 到 Agent 或业务层

## 四、核心数据契约与事实边界

### 4.1 契约职责总览

| 模型 | 职责 | 数据来源 |
|------|------|---------|
| **Canonical QueryPlan** | 当前 Turn 的唯一执行语义；只消费 runtime schema、model-scoped Catalog、runtime members、deterministic time 与 successful committed state | Grounding + deterministic StateTransition |
| **QueryResult** | Power BI 返回的结构化结果与 provenance 边界；包含 columns、rows、row_count、source_mode 等并做形状一致性校验 | Mock 或 Local MCP + Desktop，经 ToolGateway |
| **VerifiedFactSet** | 数值、结果顺序、极值、筛选、时间与 provenance 的唯一对外 factual claim authority | Canonical QueryPlan + QueryResult 确定性构建 |
| **AnswerSpec** | 自然语言答案、摘要、指标和证据 | Real 由 FactBoundedAnswerBuilder 消费 VerifiedFactSet；不得自由生成事实 |
| **ReportSpec** | 结构化报表描述；禁止任意 HTML/JS/外部脚本 | Real 只允许 VerifiedFactSet / QueryResult 可证明的 KPI、字段、rows 与 insight |
| **RenderedReport** | 报表渲染结果。包含 report_id、template_key、html 等。未来提供报表资源查看和下载引用 | Report Renderer 基于 ReportSpec 渲染 |

### 4.2 QueryPlan
normalized_question, semantic_model_key, measures, dimensions, filters (StructuredFilter), time_range, sort, top_n, comparison_mode, requested_template, inherited_context, is_mock

Real QueryPlan 的上述 canonical slots 只能由 Grounding/StateTransition 写入。Intent 与历史 QueryPlan LLM 输出只是语言 weak signal / compatibility 草稿，不能覆盖 object type、table ownership、schema fingerprint、member values 或时间边界。当前 M2 grammar 仅支持 Measure、Dimension、`EQ` Filter、resolved TimeRange、single-measure Sort/TopN；comparison、非 `EQ` operator 与通用 DAX fail closed。

### 4.3 DAXRequest
semantic_model_key, dax, max_rows, timeout_seconds, request_id, is_mock

### 4.4 QueryResult — Power BI 结果边界
result_id, semantic_model_key, columns, rows, row_count, execution_time_ms, source_mode, request_id, error (PowerBIError), truncated

内置一致性校验：row_count vs rows 长度、每行字段 vs columns 数量。

**关键规则：**
- QueryResult 是 VerifiedFactSet 的输入，不等于“任何自然语言结论均已获证明”
- 表格和图表数据必须引用 QueryResult 的实际字段与 rows
- source_mode 表示数据来源，不能因为使用真实 DeepSeek 就把 Mock QueryResult 标为 real

### 4.5 VerifiedFactSet — 对外事实 authority

VerifiedFactSet 由 Canonical QueryPlan + QueryResult 确定性构建，绑定 result/model/source、字段、row reference/aggregation、filter、time、row count、truncation 与 plan semantics。数值不得来自 LLM arithmetic 或 Answer text 反解析；TopN 只证明 QueryResult `result_position`，不把 row index 扩写成严格 business rank。无法证明的 comparison、因果、趋势或外部事实不生成。

### 4.6 AnswerSpec — 自然语言回答
answer, summary, metrics, evidence, filters, semantic_model_key, source_mode, generated_at

**关键规则：**
- Real answer 由 deterministic fact-bounded builder 从 VerifiedFactSet 构造；DAX/Answer LLM authority 与调用数均为 0
- metrics、排序/极值、筛选与时间陈述必须来自 VerifiedFactSet
- AnswerSpec 负责文字结论、摘要和指标，不承载完整表格数据
- 表格数据直接来自 QueryResult，图表的数据事实来源也是 QueryResult
- 不允许 LLM 猜测数值、排名、因果、趋势或外部事实
- evidence 提供数据来源追溯
- source_mode 与 QueryResult.source_mode 应一致

### 4.7 ReportSpec — 结构化报表
title, template_key, summary, kpis (KPISpec), charts (ChartSpec), tables (TableSpec), insights, data_source, filters, generated_at, source_mode

Real ReportSpec 的 KPI、chart fields、table projection 与 insight 必须受 VerifiedFactSet / QueryResult 约束；无法证明的 insight 省略。禁止任意 HTML、JavaScript、外部脚本、未登记模板、不存在字段。正式 Renderer 与报表资源属于 M3。

### 4.8 UserContext
user_id, roles, allowed_semantic_models, allowed_templates, allowed_tools

---

## 五、前端组合回答（M5 渲染目标）

> **本节描述 M5 前端渲染规则。** 后端 ChatResponse 已包含 answer/report/clarification/unsupported 等字段。前端根据当前 Turn 用户意图和后端实际返回产物动态渲染，不固定"文字→指标→表格→图表→报表附件"序列。

### 渲染规则

一条 AI 回答可由以下内容块按需组合：

| 类型 | 说明 | 数据来源（ChatResponse 字段） |
|------|------|------|
| `text` | 自然语言结论、总结、筛选说明、空数据提示、截断提示 | `answer` / `clarification_question` / `unsupported_reason` |
| `table` | columns、rows（来自后端 QueryResult） | `execution_audit` 或联调确定的序列化字段 |
| `chart` | bar/line/donut，仅在后端提供可视化数据时 | 后端 QueryResult 的 ChartSpec |
| `report_attachment` | report_id、title、view_reference、download_reference | `report`（ReportResponse 对象） |

### 安全限制

- 图表字段必须存在于后端 QueryResult.columns
- 图表数据必须来自后端，不允许 LLM 虚构
- 报表查看和下载引用由后端生成，**禁止** LLM 生成任意外部 URL
- source_mode 表示数据来源，不能因使用真实 DeepSeek 而将 Mock QueryResult 标为 real
- LLM 不得生成任意外部 URL 或可执行脚本
- 后端无非结构化表格/可视化数据时不生成假内容

### 当前与未来边界

| 能力 | 当前状态 | 目标轮次 |
|------|---------|---------|
| 统一前端消息 Envelope | ❌ 不存在 | M5.1 决定不新增；typed adapter 消费现有 schema |
| ChatResponse（answer/report/clarification/unsupported） | ✅ 已实现 | — |
| verified fact-bounded AnswerSpec | ✅ 已实现 | — |
| ReportSpec + ReportArtifact + view/download | ✅ M3 已实现 | — |
| 前端动态渲染 | ✅ answer/clarification/unsupported/error/empty/report | M5.1 |
| 图表前端渲染 | ⏸ 无 Chat/History ChartSpec，不伪造 | 最小契约缺口 |
| 表格前端渲染 | ⏸ 无 Chat/History QueryResult rows，不伪造 | 最小契约缺口 |
| LLM 生成 HTML/JS | ❌ 永久禁止 | — |

## 六、只读 DAX 安全与执行 authority

- Real DAX 只由 DeterministicDAXBuilder 从 Canonical QueryPlan + runtime schema 构造；LLM authority/call count 为 0
- Independent Layer 3 在执行前独立证明 exact Measure/group-by/EQ/time/TopN/ORDER BY 与无额外业务语义
- 安全层仅允许：EVALUATE、DEFINE + EVALUATE
- 禁止：SQL、写操作、跨模型引用、Python/Shell/PowerShell/JavaScript
- 安全边界来自：ToolGateway、ValidationService、semantic_model_key 白名单、Schema 字段验证、最大行数、超时、最大重试

## 七、M0.3/M2/M3 边界

| 项目 | M0.3 | M2 | M3 |
|------|------|----|----|
| PowerBIAdapter 接口 | ✅ | — | — |
| MockPowerBIAdapter | ✅ 可运行 | — | — |
| Local MCP Adapter | — | ✅ Desktop Real 链 | — |
| Remote Adapter | ✅ 骨架 | ⏸ Deferred | 仅另行批准的 production stage |
| API 数据契约 | ✅ 全部 Pydantic | — | — |
| OAuth/Token | ✅ 设计文档 | ⏸ 未实现；Local 不需要 | 仅 Remote 重新批准后 |
| 真实 DAX 查询 | ❌ | ✅ | — |
| ReportSpec Schema | ✅ 完整 | — | — |
| 生产报表模板/HTML | ❌ | ❌ | ✅ |

---

*最后更新：2026-08-21 | M5.2 Desktop discovery、runtime 与模板 override 边界修正*
