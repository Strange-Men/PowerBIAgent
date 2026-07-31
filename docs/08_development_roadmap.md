# 08 — 开发路线

> **状态：** M0.3 当前轮
> **更新频率：** 每轮结束时更新完成状态

---

## 路线总览

```
M0 开发准备 (4轮)
  M0.1 仓库初始化与文档基线        ✅ 已完成 (eb5812d)
  M0.2 智能体架构与记忆设计         ✅ 已完成 (d03ac6c)
  M0.3 数据接入与验证闭环           🔄 当前轮
  M0.4 项目骨架与阶段收尾           ⬜

MVP 功能阶段 (5轮)
  M1 真实 DeepSeek 接入             ⬜
  M2 真实 Power BI MCP 与数据问答    ⬜
  M3 报表生成闭环                   ⬜
  M4 多轮记忆完善                   ⬜
  M5 React 前端与联调                ⬜

后续阶段 (延后)
  商业化权限与部署                    ⬜
```

---

## M0.3 — 数据接入与验证闭环

**状态：** 🔄 进行中 | **Commit：** M0.3_数据接入与验证闭环

### 核心交付物

- M0.2 审计修复（AgentRuntime、PydanticAI API、Fixture、Mock LLM、IntentSpec、记忆规则）
- Power BI MCP 与 OAuth ADR-003
- PowerBIAdapter（Mock + Remote 骨架）
- 核心数据契约（QueryPlan、DAXRequest、QueryResult、AnswerSpec、ReportSpec、UserContext）
- Harness ETCLOVG 完整实现（ADR-004）
- ToolGateway、ContextBuilder、TurnController、ValidationService、TraceRecorder
- InMemoryMemoryRepository
- MockAgentRuntime、MockReportRenderer、MockTurnService
- Golden Cases（10 条）+ GoldenCaseRunner
- 166 个测试全部通过

### Tag：否

---

## M0.4 — 项目骨架与阶段收尾

**Commit：** M0.4_项目骨架与阶段收尾

### 允许

- Pydantic Settings
- FastAPI 最小骨架
- `/health`
- 运行模式展示
- Application Service 正式接入
- health 测试
- README 启动验证
- 全量审查
- M0 总验收
- 是否创建 M0 封板 Tag 由 M0.4 Prompt 决定

### 禁止

- 真实 DeepSeek
- 真实 Power BI 生产连接
- React 页面
- Docker
- 多租户
- 正式报表产品
- M1 开发

---

*最后更新：2026-07-31 | M0.3 数据接入与验证闭环*
