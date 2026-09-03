# ADR — 架构决策记录

本目录存放项目的架构决策记录（Architecture Decision Records）。

## 格式

文件名格式：`ADR-NNN_slug.md`

示例：`ADR-001_agent_framework_selection.md`

## 模板

每个 ADR 包含：
- **状态：** proposed / accepted / deprecated / superseded
- **日期：** 决策日期
- **决策者：** 决策参与人
- **背景：** 为什么需要做这个决策
- **决策内容：** 选择了什么方案
- **备选方案：** 考虑过的其他方案及其优劣
- **后果：** 决策带来的正面和负面影响

## 当前 ADR

| 编号 | 标题 | 状态 | 日期 |
|------|------|------|------|
| ADR-001 | Agent 框架选择 — PydanticAI | **superseded**（M1.6.1 废弃） | 2026-07-31 |
| ADR-002 | 记忆系统与存储方案 | accepted | 2026-07-31 |
| ADR-003 | Power BI MCP 认证与接入方案 | **partially superseded by ADR-006** | 2026-07-31 |
| ADR-004 | Harness 方案：轻量 ETCLOVG 控制面 | accepted | 2026-07-31 |
| ADR-005 | [确定性 TurnPipeline 与受控 LLM 调用架构](ADR-005_deterministic_turn_pipeline_and_controlled_llm_architecture.md) | accepted | 2026-08-04 |
| ADR-006 | [真实 Power BI Remote MCP 生产接入架构](ADR-006_remote_powerbi_mcp_production_integration.md) | accepted | 2026-08-11 |
| ADR-007 | [Demo 阶段使用 Local Power BI MCP 验证真实流程](ADR-007_local_mcp_demo_validation_path.md) | accepted | 2026-08-11 |
| ADR-008 | [Business Semantic Catalog and Grounding Authority](ADR-008_business_semantic_catalog_and_grounding_authority.md) | accepted | 2026-08-13 |
| ADR-009 | [Deterministic Query Execution and Verified Fact Authority](ADR-009_deterministic_query_execution_and_verified_fact_authority.md) | accepted | 2026-08-14 |
| ADR-010 | [Deterministic Report Template and Data Plan Authority](ADR-010_deterministic_report_template_and_data_plan_authority.md) | accepted（固定事实边界有效；固定四查询限制由 ADR-011 supersede） | 2026-08-17 |
| ADR-011 | [Adaptive Report Planning and Visualization Authority](ADR-011_adaptive_report_planning_and_visualization_authority.md) | accepted | 2026-08-17 |
| ADR-012 | [Local Persistence Architecture and Storage Foundation](ADR-012_local_persistence_architecture.md) | accepted | 2026-08-18 |
| ADR-013 | [LLM Model Profiles and Request-Scoped Provider Selection](ADR-013_llm_model_profiles_and_request_scoped_provider_selection.md) | accepted | 2026-08-27 |
| ADR-014 | [Question Routing and Query Shape Authority](ADR-014_question_routing_and_query_shape_authority.md) | accepted | 2026-08-28 |
| ADR-015 | [Cross-language Runtime Grounding](ADR-015_cross_language_runtime_grounding.md) | accepted | 2026-08-31 |
| ADR-016 | [Semantic Completeness、Result Inspection 与 Presentation Truth](ADR-016_semantic_completeness_result_inspection_and_presentation_truth.md) | accepted | 2026-09-02 |

当前开发最重要的 active 决策为 ADR-005—ADR-016：ADR-005 约束统一控制面，ADR-006/007 分别约束 Deferred Remote 与当前 Local Provider，ADR-008/009 分别约束 canonical business semantics 与 deterministic execution / VerifiedFactSet，ADR-010 约束 M3 固定事实边界（固定四查询限制由 ADR-011 supersede），ADR-011 约束自适应报表规划与可视化权限，ADR-012 约束 SQLite/Repository/HTML authority 及 M4.4 restart/delete recovery，ADR-013 约束共享 OpenAI-compatible Provider 与 request-scoped immutable profile selection，ADR-014/015 分别约束 query shape authority 与跨语言 runtime grounding，ADR-016 固化 Semantic Obligation Coverage、Canonical Shape Completeness、Result Semantic Inspection 与 Deterministic Query Scope 四个 invariant。ADR-001 已 superseded；ADR-003 仅保留未被 ADR-006 替代的历史方向。

**当前正式基线：** main（M5.8.6 COMPLETE）；m5/rebuild 已冻结为只读发布追溯分支。M5.9/M5.10 NOT STARTED。

## ADR 详情

### ADR-001 — Agent 框架选择 ⚠️ SUPERSEDED

~~选择 PydanticAI 作为单 Agent 框架。结构化输出参数名为 `output_type`（非 `result_type`）。通过 AgentRuntime Adapter 隔离框架依赖。~~

**M1.6.1 废弃，M1.6.3 正式删除。** 动态复验证实 PydanticAI 生产路径实际未使用，DeepSeekTurnService 绕过 AgentRuntime 直接调用 Provider。AgentRuntime/MockAgentRuntime 已删除，pyproject.toml 不再声明 pydantic-ai。由 ADR-005 替代。

### ADR-002 — 记忆系统与存储方案

Pydantic 数据契约 + Repository 抽象接口。四层记忆设计、三态机制、MemoryCommitEvidence 结构化证据、InMemoryMemoryRepository。Mock 与 Real 空间隔离。

### ADR-003 — Power BI MCP 认证与接入方案

Remote MCP、Entra App、PowerBIAdapter 隔离方向继续有效；Device Code、独立 MSAL、Token 缓存和 Fallback 实现部分由 ADR-006 替代。保留历史上下文。

### ADR-005 — 确定性TurnPipeline与受控LLM调用架构

正式正文见 [ADR-005 独立文件](ADR-005_deterministic_turn_pipeline_and_controlled_llm_architecture.md)。核心决策：PydanticAI 已废弃；TurnPipeline 为确定性控制面；LLM 仅受控结构化生成；ToolGateway 是 Power BI / Renderer 唯一入口；Mock 与 DeepSeek 共用执行骨架。

### ADR-006 — 真实 Power BI Remote MCP 生产接入架构

正式正文见 [ADR-006 独立文件](ADR-006_remote_powerbi_mcp_production_integration.md)。在 ADR-005 总体管线之下，固化官方 MCP Python Client、用户委托 OAuth、PowerBIAdapter 隔离、工具白名单、无静默回退及离线 CI / 人工 Smoke 边界。

### ADR-007 — Demo 阶段使用 Local Power BI MCP 验证真实流程

正式正文见 [ADR-007 独立文件](ADR-007_local_mcp_demo_validation_path.md)。管理员前置条件暂不可得时，Demo 先通过 Local MCP + Power BI Desktop 验证真实链路；ADR-006 Remote 生产化方案保持 accepted，Local / Remote 只替换 Adapter 后的 Provider。

### ADR-008 — Business Semantic Catalog and Grounding Authority

正式正文见 [ADR-008 独立文件](ADR-008_business_semantic_catalog_and_grounding_authority.md)。核心决策：runtime schema + model-scoped glossary + runtime members + deterministic time rules 是业务语义 Source of Truth；Grounding 是 canonical semantic authority；StateTransition 只负责确定性状态变化；Intent 与 QueryPlan LLM 不拥有 canonical business truth。

### ADR-009 — Deterministic Query Execution and Verified Fact Authority

正式正文见 [ADR-009 独立文件](ADR-009_deterministic_query_execution_and_verified_fact_authority.md)。核心决策：Real canonical path 只使用受限 Deterministic DAX Builder；Independent Layer 3 独立验证执行语义；VerifiedFactSet 是 Answer/Report factual claim 的唯一 authority。

### ADR-010 — Deterministic Report Template and Data Plan Authority

正式正文见 [ADR-010 独立文件](ADR-010_deterministic_report_template_and_data_plan_authority.md)。核心决策：M3 只提供 `sales_report`；TemplateContract 固定 schema 要求与查询需求，ReportDataPlan 不读取 LLM draft，每个查询继续复用 M2 确定性执行与事实链。固定事实安全边界继续有效；"一个 template 永久绑定一个 model fingerprint + 固定四 queries"限制由 ADR-011 supersede。

### ADR-011 — Adaptive Report Planning and Visualization Authority

正式正文见 [ADR-011 独立文件](ADR-011_adaptive_report_planning_and_visualization_authority.md)。核心决策：固定模板 = 固定设计规则 + 允许能力目录，不是固定输出内容；section 由用户需求 ∩ runtime schema 能力 ∩ allowed catalog 决定；capability engine schema-aware；Report Intent weak signal 只输出 registry-owned ID；Visualization/Layout/Theme Policy 由普通代码决定；ReportSpec 最小结构化扩展并修正 Renderer 拒绝 charts 的历史限制。

### ADR-012 — Local Persistence Architecture and Storage Foundation

正式正文见 [ADR-012 独立文件](ADR-012_local_persistence_architecture.md)。核心决策：SQLite + SQLAlchemy Async + aiosqlite + Alembic 技术栈；数据库是 persistence provider，不是新的 business authority；ORM 持久化模型与业务 domain model 分离；JSON TEXT 列保存结构化 payload；HTML 文件继续存在文件系统；M4.4 以 terminal Snapshot、filesystem HTML 与 durable delete intent 固化 restart/crash recovery boundary。

### ADR-013 — LLM Model Profiles and Request-Scoped Provider Selection

正式正文见 [ADR-013 独立文件](ADR-013_llm_model_profiles_and_request_scoped_provider_selection.md)。核心决策：DeepSeek/Kimi 共享 OpenAI-compatible Provider；profile 是不可变协议/模型配置；每轮显式解析并固定 snapshot，禁止全局 mutable default、隐式混用与自动 fallback；provider 永不取得 semantic/DAX/factual authority。

### ADR-014 — Question Routing and Query Shape Authority

正式正文见 [ADR-014 独立文件](ADR-014_question_routing_and_query_shape_authority.md)。核心决策：Question Router 只分类能力且不拥有业务对象/事实权威；Query Shape 只决定 required slots；非业务请求 ZERO Power BI 与 semantic Memory mutation；dimension-only、runtime-validated member set、Top1 与 bounded trend 继续由 Canonical QueryPlan、Deterministic DAX 和独立 verifier 证明。

### ADR-004 — Harness 方案：轻量 ETCLOVG 控制面

Execution、Tooling、Context、Lifecycle、Observability、Verification、Governance 七层职责。无 Docker/LangGraph/OpenTelemetry。

---

*最后更新：2026-08-31 | ADR-015 扩展现有跨语言 Grounding；ADR-008/009 factual authority 不变*
