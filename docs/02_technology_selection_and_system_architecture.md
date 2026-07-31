# 02 — 技术选型与系统架构

> **状态：** M0.3 已更新
> **当前轮次：** M0.3 数据接入与验证闭环
> **关联 ADR：** ADR-001、ADR-002、ADR-003、ADR-004

---

## 一、技术选型概览

| 层级 | 技术 | 版本 | 状态 |
|------|------|------|------|
| 前端框架 | React + Vite | — | 已确定，M5 开发 |
| 后端框架 | FastAPI | — | 已确定，M0.4 最小骨架 |
| Agent 框架 | PydanticAI | 2.21.0 | ✅ M0.2 选定，Adapter 隔离 |
| LLM Provider | DeepSeek + Mock | — | ✅ Mock 可运行，DeepSeek M1 |
| Power BI | Remote MCP Server | — | M2 真实连接，M0.3 Mock |
| 数据校验 | Pydantic v2 | 2.13.4 | ✅ 已锁定 |
| 记忆存储 | Repository + 内存 | — | ✅ M0.3 InMemory 实现 |
| 报表渲染 | Mock HTML | — | M0.3 最小实现，M3 正式 |
| Harness | ETCLOVG 轻量 | — | ✅ M0.3 完整实现 |
| 测试框架 | pytest + pytest-asyncio | 9.1.1 / 1.4.0 | ✅ 已锁定 |
| Golden Cases | YAML + Runner | — | ✅ M0.3 10 条 Cases |
| 依赖锁定 | PyYAML | 6.0.3 | ✅ M0.3 新增 |

## 二、系统架构

```
┌──────────────────────────────────────────────────────────┐
│                      前端 (React + Vite)                   │
│              前端开发延后至后端核心链路跑通                    │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP/SSE
                       ▼
┌──────────────────────────────────────────────────────────┐
│                    API 层 (FastAPI)                        │
│  M0.4: GET /api/health                                    │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│                Application 层                              │
│  MockTurnService (M0.3) → FastAPI Service (M0.4)          │
└──────────────────────┬───────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
┌────────────┐ ┌───────────┐ ┌──────────────┐
│ Harness    │ │ Agent     │ │ Power BI     │
│ ETCLOVG    │ │ Runtime   │ │ Adapter      │
│            │ │           │ │              │
│ ToolGateway│ │ Mock (M0.3)│ │ Mock (M0.3) │
│ ContextBld │ │ DeepSeek   │ │ Remote (M2) │
│ TurnCtrl   │ │ (M1)      │ │              │
│ Validation │ │           │ │              │
│ Trace      │ │           │ │              │
└────────────┘ └───────────┘ └──────────────┘
         │             │             │
         ▼             ▼             ▼
┌────────────┐ ┌───────────┐ ┌──────────────┐
│ Memory     │ │ Report    │ │ Schemas      │
│ Repository │ │ Renderer  │ │ Contracts    │
│            │ │           │ │              │
│ InMemory   │ │ Mock (0.3)│ │ QueryPlan    │
│ (M0.3)     │ │ Jinja2(M3)│ │ DAXRequest   │
│            │ │           │ │ QueryResult  │
│            │ │           │ │ AnswerSpec   │
│            │ │           │ │ ReportSpec   │
└────────────┘ └───────────┘ └──────────────┘
```

## 三、ADR 编号（已修正）

| ADR | 标题 | 状态 |
|-----|------|------|
| ADR-001 | Agent 框架选择 — PydanticAI | accepted |
| ADR-002 | 记忆系统与存储方案 | accepted |
| ADR-003 | Power BI MCP 认证与接入方案 | accepted |
| ADR-004 | Harness 方案：轻量 ETCLOVG 控制面 | accepted |

## 四、模块边界

### M0.1 完成
- 仓库初始化、文档基线、环境搭建

### M0.2 完成
- Agent 框架 ADR、LLM Provider、IntentSpec、记忆系统设计、65 测试

### M0.3 完成
- M0.2 审计修复（AgentRuntime、PydanticAI API、Fixture、Mock LLM、IntentSpec、记忆规则）
- PowerBIAdapter（Mock + Remote 骨架）
- 核心数据契约（QueryPlan、DAXRequest、QueryResult、AnswerSpec、ReportSpec、UserContext）
- Harness ETCLOVG 完整实现（ToolGateway、ContextBuilder、TurnController、ValidationService、TraceRecorder）
- InMemoryMemoryRepository
- MockAgentRuntime、MockReportRenderer、MockTurnService
- Golden Cases（10 条）+ GoldenCaseRunner
- 166 个测试全部通过

### M0.4 允许
- FastAPI 最小骨架、`/health`、Pydantic Settings、全量审查与封板

---

*最后更新：2026-07-31 | M0.3 数据接入与验证闭环*
