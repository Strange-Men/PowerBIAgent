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

## ADR 详情

### ADR-001 — Agent 框架选择

选择 PydanticAI 作为单 Agent 框架。比较了 PydanticAI、Microsoft Semantic Kernel 和手写 Agent Loop。PydanticAI 在 Python 原生性、Pydantic 集成、DeepSeek 兼容、Mock 友好性和轻量程度上占优。

### ADR-002 — 记忆系统与存储方案

选择 Pydantic 数据契约 + Repository 抽象接口，M0.2 不实现 SQLite 持久化。四层记忆设计（原始对话、结构化工作记忆、滚动摘要、查询产物）。三态机制（pending/committed/failed）。request_id 幂等 + memory_version 乐观锁。

---

*最后更新：2026-07-31 | M0.2 智能体架构与记忆设计*
