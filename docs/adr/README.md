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

### ADR-004 — Harness 方案：轻量 ETCLOVG 控制面

Execution、Tooling、Context、Lifecycle、Observability、Verification、Governance 七层职责。无 Docker/LangGraph/OpenTelemetry。

---

*最后更新：2026-08-11 | M2.0 ADR-005 正式文件化与 ADR-006 接入决策*
