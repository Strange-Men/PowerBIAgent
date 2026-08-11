# ADR-005 — 确定性 TurnPipeline 与受控 LLM 调用架构

- **状态：** accepted
- **日期：** 2026-08-04
- **决策者：** 用户明确批准

---

## 背景

M1.5 全链路验收后动态复验发现：PydanticAI 生产路径实际未使用、DeepSeek 绕过 ToolGateway 和 ContextBuilder、TurnController 限制未生效、Mock 与 DeepSeek 存在双管线。

## 决策内容

1. 废弃 PydanticAI 作为生产 Agent 框架（ADR-001 → superseded）。
2. 采用确定性 TurnPipeline 控制对话生命周期（非 LLM 自主 Agent 循环）。
3. LLM 只负责受约束的结构化生成（Intent、QueryPlan、DAX、Answer、ReportSpec）。
4. ToolGateway 是 Power BI 和 Renderer 的唯一调用入口。
5. Mock 与 DeepSeek 共享同一执行骨架，只替换 Provider、Adapter 或 Fixture。

## 备选方案

- 继续使用 PydanticAI 并修复所有绕过问题 → 拒绝，PydanticAI Agent 循环模型不适合确定性管线需求。
- 从零手写 Agent Runtime → 拒绝，违反项目铁律。
- 引入 LangGraph → 拒绝，违反项目铁律。

## 后果

- 正面：管线行为可预测、可测试；Mock/DeepSeek 一致性有保障；Harness 约束可统一生效。
- 负面：需要 M1.6.2—M1.6.3.1 多轮代码整改；PydanticAI 和旧 Agent 抽象（AgentRuntime/MockAgentRuntime）已由 M1.6.3 正式删除；TurnPipeline 控制面在 M1.6.3.1 真正统一。
- 代码整改范围：M1.6.2 Harness 与配置收口（已完成）、M1.6.3 统一 TurnPipeline 与旧 Agent 抽象清理（已完成）。

---

*本文件由原 `docs/adr/README.md` 中 ADR-005 权威正文迁移形成；决策语义未改变。*
