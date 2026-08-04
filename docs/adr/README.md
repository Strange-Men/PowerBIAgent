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
| ADR-003 | Power BI MCP 认证与接入方案 | accepted | 2026-07-31 |
| ADR-004 | Harness 方案：轻量 ETCLOVG 控制面 | accepted | 2026-07-31 |
| ADR-005 | 确定性TurnPipeline与受控LLM调用架构 | accepted | 2026-08-04 |

## ADR 详情

### ADR-001 — Agent 框架选择 ⚠️ SUPERSEDED

~~选择 PydanticAI 作为单 Agent 框架。结构化输出参数名为 `output_type`（非 `result_type`）。通过 AgentRuntime Adapter 隔离框架依赖。~~

**M1.6.1 废弃。** 动态复验证实 PydanticAI 生产路径实际未使用，DeepSeekTurnService 绕过 AgentRuntime 直接调用 Provider。由 ADR-005 替代。

### ADR-002 — 记忆系统与存储方案

Pydantic 数据契约 + Repository 抽象接口。四层记忆设计、三态机制、MemoryCommitEvidence 结构化证据、InMemoryMemoryRepository。Mock 与 Real 空间隔离。

### ADR-003 — Power BI MCP 认证与接入方案

使用 Remote MCP Server + MSAL device code flow。OAuth 风险、Entra App Registration、VS Code 与自定义客户端差异已明确。M0.3 仅设计、接口、Mock 和 Remote 骨架。

### ADR-005 — 确定性TurnPipeline与受控LLM调用架构

**状态：** accepted | **日期：** 2026-08-04 | **决策者：** 用户明确批准

**背景：** M1.5 全链路验收后动态复验发现：PydanticAI 生产路径实际未使用、DeepSeek 绕过 ToolGateway 和 ContextBuilder、TurnController 限制未生效、Mock 与 DeepSeek 存在双管线。

**决策内容：**
1. 废弃 PydanticAI 作为生产 Agent 框架（ADR-001 → superseded）
2. 采用确定性 TurnPipeline 控制对话生命周期（非 LLM 自主 Agent 循环）
3. LLM 只负责受约束的结构化生成（Intent、QueryPlan、DAX、Answer、ReportSpec）
4. ToolGateway 是 Power BI 和 Renderer 的唯一调用入口
5. Mock 与 DeepSeek 共享同一执行骨架，只替换 Provider、Adapter 或 Fixture

**备选方案：**
- 继续使用 PydanticAI 并修复所有绕过问题 → 拒绝，PydanticAI Agent 循环模型不适合确定性管线需求
- 从零手写 Agent Runtime → 拒绝，违反项目铁律
- 引入 LangGraph → 拒绝，违反项目铁律

**后果：**
- 正面：管线行为可预测、可测试；Mock/DeepSeek 一致性有保障；Harness 约束可统一生效
- 负面：需要 M1.6.2—M1.6.3 两轮代码整改；PydanticAI 依赖需保留但不再作为生产路径
- 代码整改范围：M1.6.2 Harness 与配置收口、M1.6.3 统一 TurnPipeline 与旧 Agent 抽象清理

### ADR-004 — Harness 方案：轻量 ETCLOVG 控制面

Execution、Tooling、Context、Lifecycle、Observability、Verification、Governance 七层职责。无 Docker/LangGraph/OpenTelemetry。

---

*最后更新：2026-08-04 | M1.6.1 审计复验与架构定案*
