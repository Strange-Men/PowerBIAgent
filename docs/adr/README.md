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
| ADR-001 | Agent 框架选择 — PydanticAI | accepted | 2026-07-31 |
| ADR-002 | 记忆系统与存储方案 | accepted | 2026-07-31 |
| ADR-003 | Power BI MCP 认证与接入方案 | accepted | 2026-07-31 |
| ADR-004 | Harness 方案：轻量 ETCLOVG 控制面 | accepted | 2026-07-31 |

## ADR 详情

### ADR-001 — Agent 框架选择

选择 PydanticAI 作为单 Agent 框架。结构化输出参数名为 `output_type`（非 `result_type`）。通过 AgentRuntime Adapter 隔离框架依赖。

### ADR-002 — 记忆系统与存储方案

Pydantic 数据契约 + Repository 抽象接口。四层记忆设计、三态机制、MemoryCommitEvidence 结构化证据、InMemoryMemoryRepository。Mock 与 Real 空间隔离。

### ADR-003 — Power BI MCP 认证与接入方案

使用 Remote MCP Server + MSAL device code flow。OAuth 风险、Entra App Registration、VS Code 与自定义客户端差异已明确。M0.3 仅设计、接口、Mock 和 Remote 骨架。

### ADR-004 — Harness 方案：轻量 ETCLOVG 控制面

Execution、Tooling、Context、Lifecycle、Observability、Verification、Governance 七层职责。无 Docker/LangGraph/OpenTelemetry。

---

*最后更新：2026-07-31 | M0.3 数据接入与验证闭环*
