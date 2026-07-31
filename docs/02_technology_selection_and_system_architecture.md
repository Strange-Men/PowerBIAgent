# 02 — 技术选型与系统架构

> **状态：** M0.2 已更新实质性内容
> **下一轮：** M0.3（Power BI MCP Adapter、Harness）
> **关联 ADR：** ADR-001（Agent 框架）、ADR-002（记忆系统）

---

## 一、技术选型概览

| 层级 | 候选技术 | 状态 | 决策轮次 |
|------|---------|------|---------|
| 前端框架 | React + Vite | ✅ 已确定 | PRD |
| 后端框架 | FastAPI | ✅ 已确定 | PRD |
| Agent 框架 | PydanticAI 2.21.0 | ✅ 已确定 | M0.2 (ADR-001) |
| LLM Provider | DeepSeek + Mock | ✅ Mock 可运行，DeepSeek 骨架 | M0.2 |
| LLM SDK | PydanticAI + OpenAI-compatible | ✅ 已确定 | M0.2 |
| Power BI MCP | MCP Client | ⏳ 待定 | M0.3 |
| 数据校验 | Pydantic v2 | ✅ 方向已定 | PRD |
| 记忆存储 | Repository 接口 + 内存实现（MVP） | ✅ 契约已定，持久化延后 | M0.2 (ADR-002) |
| 报表渲染 | Jinja2 固定模板 | ⏳ 待确认 | M3 |
| 测试框架 | pytest + pytest-asyncio | ✅ 已确认（65 单测通过） | M0.2 |

## 二、系统架构概要

```
┌──────────────────────────────────────────────────────────┐
│                      前端 (React + Vite)                   │
│                   极简白色对话页面                           │
│              前端开发延后至后端核心链路跑通                    │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP/SSE
                       ▼
┌──────────────────────────────────────────────────────────┐
│                    API 层 (FastAPI)                        │
│  GET /api/health                                           │
│  GET /api/semantic-models                                  │
│  GET /api/report-templates                                 │
│  POST /api/chat                                            │
│  GET /api/reports/{report_id}                              │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│                  Agent 编排层 (单Agent)                     │
│                                                           │
│  ┌─────────────┐  ┌──────────┐  ┌────────────────────┐   │
│  │ 意图识别      │  │ 工具调度  │  │ 输出验证           │   │
│  │ IntentSpec   │  │ ToolGateway│  │ AnswerSpec/ReportSpec│ │
│  └─────────────┘  └──────────┘  └────────────────────┘   │
└──────┬──────────────┬──────────────┬─────────────────────┘
       │              │              │
       ▼              ▼              ▼
┌──────────┐  ┌────────────┐  ┌──────────────┐
│ LLM      │  │ Power BI   │  │ Memory       │
│ Provider │  │ MCP Adapter│  │ Repository   │
│          │  │            │  │              │
│ DeepSeek │  │ MCP Client │  │ SQLite       │
│ Mock LLM │  │ DAX Exec   │  │ Session Store│
└──────────┘  └────────────┘  └──────────────┘
       │              │              │
       ▼              ▼              ▼
┌──────────┐  ┌────────────┐  ┌──────────────┐
│ Harness  │  │ 报表引擎    │  │ Trace        │
│          │  │            │  │              │
│ 工具白名单 │  │ 固定模板    │  │ 请求全链路    │
│ 超时/行数 │  │ Jinja2     │  │ 耗时记录     │
│ Golden   │  │ HTML Render│  │ 错误记录     │
│ Cases    │  │            │  │              │
└──────────┘  └────────────┘  └──────────────┘
```

## 三、待完成的 ADR

以下架构决策需要在对应轮次通过 ADR 正式确定：

| ADR | 决策内容 | 计划轮次 |
|-----|---------|---------|
| ADR-0001 | Agent 框架选择 | M0.2 |
| ADR-0002 | LLM Provider 接口设计 | M0.2 |
| ADR-0003 | Mock LLM 策略 | M0.2 |
| ADR-0004 | 意图识别方案 | M0.2 |
| ADR-0005 | 记忆系统设计 | M0.2 |
| ADR-0006 | Power BI MCP Client 实现方案 | M0.3 |
| ADR-0007 | Harness 架构 | M0.3/M0.4 |

## 四、模块边界

### 本轮 (M0.1) 边界

- 仅建立架构概要骨架
- 不选择具体 Agent 框架
- 不实现任何模块代码
- 不编写 ADR

### 后续轮次边界

- M0.2：完成 Agent 框架 ADR、LLM Provider 设计、意图识别设计、记忆系统设计
- M0.3：完成 Power BI MCP Adapter、Mock 适配器、Harness 完整闭环（ETCLOVG）、Golden Cases
- M0.4：FastAPI 最小骨架、`/health`、全量测试、文档代码一致性、M0 总验收

---

*创建日期：2026-07-31 | M0.1 仓库初始化与文档基线*
