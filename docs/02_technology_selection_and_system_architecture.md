# 02 — 技术选型与系统架构

> **状态：** M2.6.4 — M0—M2 ready for final seal；Final Tag 待用户授权
> **当前轮次：** M2.6.4
> **关联 ADR：** ADR-001（已废弃）、ADR-002—ADR-009；当前以 ADR-005—ADR-009 为准

---

## 一、技术选型概览

| 层级 | 技术 | 版本 | 状态 |
|------|------|------|------|
| 前端框架 | React + Vite | — | 已确定，M5 开发 |
| 后端框架 | FastAPI | — | 已确定，M0.4 最小骨架 |
| Agent 框架 | 确定性 TurnPipeline（自研） | — | ✅ M1.6.3.1 控制面真正统一，PydanticAI 已删除（ADR-001→superseded） |
| LLM Provider | DeepSeek + Mock | — | ✅ Real: Intent/语言草稿/受限候选选择；Real DAX authority=0 |
| Power BI | Local MCP + Desktop | beta.12 实机基线 | ✅ 当前 Real Demo；Remote Deferred |
| 数据校验 | Pydantic v2 | 2.13.4 | ✅ 已锁定 |
| 记忆存储 | Repository + 内存 | — | ✅ M0.3 InMemory 实现 |
| 报表渲染 | Mock HTML | — | M0.3 最小实现，M3 正式 |
| Harness | ETCLOVG 轻量 | — | ✅ M0.3 完整实现 |
| 测试框架 | pytest + pytest-asyncio | 9.1.1 / 1.4.0 | ✅ 已锁定 |
| Golden Cases | YAML + Runner | — | ✅ M0.3 10 条 Cases |
| 依赖锁定 | PyYAML | 6.0.3 | ✅ M0.3 新增 |

## 二、系统架构

> 下图是 M0/M1 历史分层快照，其中 Agent Runtime、Remote 主路径和 LLM DAX/Answer authority 已被 ADR-005、ADR-007、ADR-008、ADR-009 supersede。当前权威链为 `TurnPipeline → Grounding → Canonical QueryPlan → Deterministic DAX → Independent Layer 3 → QueryResult → VerifiedFactSet`。

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
| ADR-001 | Agent 框架选择 — PydanticAI | superseded（M1.6.1 废弃，由 ADR-005 替代） |
| ADR-002 | 记忆系统与存储方案 | accepted |
| ADR-003 | Power BI MCP 认证与接入方案 | partially superseded by ADR-006 |
| ADR-004 | Harness 方案：轻量 ETCLOVG 控制面 | accepted |
| ADR-005 | 确定性TurnPipeline与受控LLM调用架构 | accepted（M1.6.1） |
| ADR-006 | Remote Power BI MCP 生产接入 | accepted / Deferred implementation |
| ADR-007 | Local MCP Demo 验证路径 | accepted / active |
| ADR-008 | Business Semantic Catalog and Grounding Authority | accepted / active |
| ADR-009 | Deterministic Execution and Verified Fact Authority | accepted / active |

## 四、M1.6.1 架构定案（2026-08-04）

### 背景

M1.5 全链路验收后，动态复验证实以下问题：
- PydanticAI 生产路径实际未使用（DeepSeekTurnService 绕过 AgentRuntime 直接调用 Provider）
- DeepSeek 绕过 ToolGateway 和 ContextBuilder
- TurnController 限制未生效
- Mock 与 DeepSeek 存在事实上的双管线

### 架构决定（本轮已确认，用户明确批准）

1. **废弃并删除 PydanticAI**（ADR-001 → superseded）。AgentRuntime/MockAgentRuntime 已彻底删除，pyproject.toml 不再声明 pydantic-ai 依赖。
2. **采用确定性 TurnPipeline 控制生命周期**。当前 Real 阶段顺序由 ADR-008/009 扩展为 Intent → Grounding → Canonical QueryPlan → Deterministic DAX → VerifiedFactSet → factual output，LLM 不控制流程分支。
3. **LLM 只负责受约束语言任务**。M1 的 DAX/Answer/ReportSpec 生成描述仅保留 Mock compatibility；Real DAX 和外部事实输出已由 ADR-009 收回普通代码。
4. **ToolGateway 是唯一调用入口**。所有 Power BI 和 Renderer 调用必须经过 ToolGateway，DeepSeek 路径已纳入。
5. **Mock 与 DeepSeek 共享同一执行骨架**。共享 TurnPipeline 统一 ID 生成、指纹、幂等、ContextBuilder、ToolGateway、TurnController、Memory、Snapshot。只替换 Provider/Adapter/Fixture。

### 实施状态

| 决定 | 状态 |
|------|------|
| 架构方向定案 | ✅ 已完成（M1.6.1, `0f6424f`） |
| Harness 与配置收口 | ✅ 已完成（M1.6.2, `208bca4`） |
| TurnPipeline 统一实现 | ✅ 已完成（M1.6.3） |
| 旧 Agent 抽象清理 | ✅ 已完成（M1.6.3：AgentRuntime、MockAgentRuntime 已删除，PydanticAI 依赖已移除；M1.6.3.1：TurnPipeline 控制面真正统一） |
| AI 真实性与对抗测试 | ⬜ M1.6.4 |
| CI 与全量回归 | ⬜ M1.6.5 |

### 当前代码实际状态（M1.6.3 基线）

- `TurnPipeline` 类统一 Mock 与 DeepSeek 执行骨架（`backend/app/application/turn_pipeline.py`）
- `DeepSeekTurnService` 通过 ToolGateway 调用 Power BI 和 Renderer
- `ContextBuilder` 在 Mock 和 DeepSeek 两条路径均生效
- `TurnController` 限制在 DeepSeek 路径真实生效
- Mock 使用 `MockLLMProvider` 直接调用（`_LLMProviderAdapter` 保持测试兼容）
- PydanticAI 依赖已从 pyproject.toml 移除，`backend/app/agent/` 目录已删除

## 五、模块边界

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

*最后更新：2026-08-14 | M2.6.4 current architecture marker；历史分层由 ADR-005—ADR-009 supersede*
