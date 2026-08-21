# PowerBIAgent

[![PowerBIAgent Validation](https://github.com/Strange-Men/PowerBIAgent/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Strange-Men/PowerBIAgent/actions/workflows/ci.yml)
![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)

面向 Power BI 语义模型的自然语言分析后端，以确定性事实链提供数据问答、固定模板报表和可恢复的多轮会话。

当前版本：**M5.1 — React 前端实现与核心联调**。M4.4.2 FINAL PASS；M5.1 已完成；M5.2 NOT STARTED。

## Overview

PowerBIAgent 面向公司内部少量、不熟悉 Power BI 或 DAX 的业务用户。用户用自然语言提出数据问题或报表需求；FastAPI 后端负责语义落地、受限 DAX 构造、Power BI 查询、事实验证、回答与静态 HTML 报表生成。

当前产品形态是 Windows 本地单机 MVP：支持 Mock 离线开发，也支持 DeepSeek + Local MCP + Power BI Desktop 真实链。M5.1 已提供 React 对话前端，并通过 Vite proxy 接入 FastAPI。

## Highlights

- 自然语言 Power BI 数据问答，Mock 与 Real 共用同一 TurnPipeline 执行骨架。
- Business Semantic Grounding 将用户表达绑定到 runtime schema、model-scoped glossary 与 runtime members。
- Real DAX 由受限 deterministic builder 生成，并在 Power BI 执行前经过独立 Layer 3 验证。
- `VerifiedFactSet` 是数值、结果顺序、筛选、时间与 provenance 的唯一对外事实边界。
- `sales_report` 根据用户需求与 runtime capability 生成 KPI、趋势、贡献、对比和排行等固定设计报表。
- Structured multi-turn Memory 只在完整成功后提交；歧义、失败和 clarification 不污染 committed state。
- SQLite 提供重启恢复、结构化 history/search/archive/delete 与 crash-safe delete retry。
- `(runtime_mode, conversation_id)` 和 `(source_mode, conversation_id)` 严格隔离 Mock/Real 状态与报表历史。

## How It Works

```mermaid
flowchart LR
    User["User"] --> API["FastAPI"]
    API --> Pipeline["TurnPipeline"]
    Pipeline --> Grounding["Intent / Grounding"]
    Grounding --> Plan["Canonical QueryPlan"]
    Plan --> DAX["Deterministic DAX"]
    DAX --> PBI["Power BI"]
    PBI --> Result["QueryResult"]
    Result --> Facts["VerifiedFactSet"]
    Facts --> Output["Answer / Report"]
    Output --> State["Memory / Snapshot"]
```

LLM 负责受约束的语言理解；runtime schema、确定性代码、Power BI、`QueryResult` 与 `VerifiedFactSet` 负责事实真值。Power BI 调用只能经过 `ToolGateway → PowerBIAdapter`，Real 失败不会静默回退 Mock。

## Truth Boundary

| LLM 可以 | LLM 不可以 |
|---|---|
| Intent 与受约束语言理解 | 发明业务语义或 runtime 对象 |
| 在 Catalog-owned candidate ID 中 bounded selection | 生成 authoritative Real DAX |
| 生成受事实约束的语言草稿 | 发明 QueryResult、数字、排名、趋势或因果 |
| 输出 registry-owned report-intent weak signal | 生成任意 HTML、JavaScript 或报表事实 |

Canonical authority 来自 runtime schema、Business Semantic Catalog、确定性 Grounding/StateTransition、Deterministic DAX、Power BI、`QueryResult` 与 `VerifiedFactSet`。SQLite persistence/history 不是 business factual authority。

## Current Capabilities

| 领域 | 已实现能力 |
|---|---|
| Data Q&A | Measure、Dimension、`EQ` filter、确定性时间范围、single-measure Sort/TopN 的受限自然语言查询 |
| Reports | 唯一 production template `sales_report`；schema-aware capability planning；固定安全 static HTML；view/download resource |
| Multi-turn Memory | 指标、维度、filter、time、sort、TopN 继承；Pending clarification 与 committed Memory 分离；损坏 canonical filter fail closed |
| Persistence & Recovery | SQLite Memory/Snapshot/report metadata；restart replay；incomplete crash witness fail closed；durable delete intent |
| History / Search | SQLite-only recent、structured history、bounded search、archive、delete；不伪造逐字 transcript |
| Local Power BI | DeepSeek + readonly Local Modeling MCP + Power BI Desktop；Real DAX/factual LLM authority 为 0 |
| React Web UI | GPT 式对话页面、可折叠 Sidebar、Composer、DeepSeek 单选、Chat/History/Search/Reports 联调与动态 terminal-state 渲染 |

Remote MCP 继续 Deferred。M5.2 视觉与交互最终收口尚未开始。

## Quick Start

### Prerequisites

- Windows 本地环境。
- Python 3.11；仓库固定 Conda 环境名为 `PBIAgent`（Conda 安装于 `D:\Conda`）。
- Mock 后端不需要 API Key 或 Power BI Desktop；运行 React 前端需要 Node.js 20.19+。
- Real Local MCP 需要 Node.js 20+、npm/npx、Power BI Desktop，以及已打开的测试 PBIX。

### Conda 初始化（首次使用）

PowerShell 中若 `conda activate` 后 `python` 仍指向 base 而不是 PBIAgent，说明缺少 conda PowerShell 初始化。**只需执行一次**：

```powershell
conda init powershell
# 然后关闭并重新打开 PowerShell 窗口
```

初始化后，`conda activate` 会正确切换 Python 路径。验证方法：

```powershell
conda activate PBIAgent
python -c "import sys; print(sys.executable)"
# 应输出：D:\Conda\envs\PBIAgent\python.exe
# 而非：D:\Conda\python.exe
```

**如果 `python` 路径不正确**，说明 PowerShell profile 未加载。排查步骤：
1. 检查 profile 是否存在：`Test-Path $PROFILE`
2. 重新打开终端（profile 只在启动时加载）
3. 或执行 `. $PROFILE` 手动加载后重新 activate

### Install

```powershell
D:\Conda\Scripts\conda.exe env create -f environment.yml
D:\Conda\envs\PBIAgent\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
conda activate PBIAgent
```

`.env.example` 是唯一可提交的配置模板。Mock 默认配置可直接运行；真实 Secret 只由用户写入本地 `.env`，不得提交或输出。

### Run

**确认 Python 路径正确后**启动后端：

```powershell
conda activate PBIAgent
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

另开终端启动前端：

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`。Vite 开发服务器将 `/api` 与 `/health` 代理到 `127.0.0.1:8000`。SQLite history/search 需要后端设置 `PERSISTENCE_BACKEND=sqlite`；前端 runtime namespace 默认 `real`，Mock 联调时显式设置 `VITE_RUNTIME_MODE=mock`。

```powershell
curl.exe http://127.0.0.1:8000/health

curl.exe -X POST http://127.0.0.1:8000/api/v1/chat `
  -H "Content-Type: application/json" `
  -d '{"message":"本月销售额是多少？"}'
```

`/health` 只验证配置是否足以创建当前 runtime，不探测 Power BI Desktop 是否在线。`DEBUG=true` 时可访问 `http://127.0.0.1:8000/docs`；关闭 debug 后 Swagger/ReDoc 不暴露。

### 常见启动问题

#### `No module named uvicorn`

使用 `python -m uvicorn ...` 时报错，但 `conda run -n PBIAgent python -m uvicorn ...` 正常。
**原因：** PowerShell 的 `conda activate` 未生效，Python 仍解析到 base 环境（`D:\Conda\python.exe`）。
**解决：** 执行 `conda init powershell` 一次 → 关闭并重新打开 PowerShell → 确认 `python -c "import sys; print(sys.executable)"` 输出 `D:\Conda\envs\PBIAgent\python.exe`。

作为一个一次性 workaround，也可用绝对路径直启动：

```powershell
D:\Conda\envs\PBIAgent\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

#### `Errno 10048` / 端口 8000 已占用

**原因：** 上次启动的后端进程未退出。
**排查与关闭：**

```powershell
# 查看谁占了 8000 端口
netstat -ano | Select-String ':8000' | Select-String 'LISTENING'

# 确认是 uvicorn 进程后关闭（替换 PID 为实际值）
Stop-Process -Id <PID> -Force

# 或直接通过端口查找并关闭
$pid = (netstat -ano | Select-String ':8000' | Select-String 'LISTENING' | ForEach-Object { $_ -split '\s+' } | Select-Object -Last 1)
Stop-Process -Id $pid -Force
```

**注意：** `Stop-Process` 按 PID 关闭，确认 PID 对应的进程名是 `python` 且命令行含 `uvicorn` 再执行。不要误杀其他程序。

#### 如何确认当前 Python 路径正确

```powershell
conda activate PBIAgent
python -c "import sys; print(sys.executable)"
# 期望输出：D:\Conda\envs\PBIAgent\python.exe
```

如果输出是 `D:\Conda\python.exe`，说明 activate 未生效，参照上一条执行 `conda init powershell`。

### Real Local MCP

在本地 `.env` 中将 `LLM_MODE=deepseek`、`POWERBI_MODE=local_mcp`，由用户填写 `DEEPSEEK_API_KEY`，并保持 `POWERBI_LOCAL_MCP_READONLY=true`。仓库固定实机基线为 `@microsoft/powerbi-modeling-mcp@0.5.0-beta.12`；详细前置、Smoke 与故障分类见 [Power BI MCP 与 API 契约](docs/04_powerbi_mcp_and_api_contracts.md) 和 [M2 集成计划](docs/milestones/m2/12_m2_powerbi_mcp_integration_plan.md)。

## Runtime Modes

| `LLM_MODE` | `POWERBI_MODE` | 用途 |
|---|---|---|
| `mock` | `mock` | 默认离线开发与 CI，无 Secret |
| `deepseek` | `mock` | 真实语言模型 + Mock Power BI 数据 |
| `deepseek` | `local_mcp` | 真实 DeepSeek + readonly Local MCP + Power BI Desktop |

`remote_mcp` 当前不可用。`PERSISTENCE_BACKEND=memory` 是 compatibility/default，只保留进程内状态；需要 restart recovery、history 或 search 时必须显式使用 `PERSISTENCE_BACKEND=sqlite`。

## API

| Method | Path / field | 说明 |
|---|---|---|
| `GET` | `/health` | 当前 runtime 配置就绪状态 |
| `POST` | `/api/v1/chat` | 非流式数据问答与报表生成 |
| field | `semantic_model_key` | 在 chat request 中选择语义模型；当前无独立 discovery endpoint |
| field | `report_template_key` | 在 chat request 中选择固定模板；当前无独立 discovery endpoint |
| `GET` | `/api/reports/{report_id}` | 查看 repository-owned HTML 报表 |
| `GET` | `/api/reports/{report_id}/download` | 下载 UTF-8 HTML 报表 |
| `GET` | `/api/v1/conversations` | 按 `runtime_mode` 查询最近会话 |
| `GET` | `/api/v1/conversations/search` | 按 `runtime_mode` 搜索声明范围内的持久化字段 |
| `GET` | `/api/v1/conversations/{conversation_id}/history` | 结构化 persisted turn history，不是 transcript |
| `GET` | `/api/v1/conversations/{conversation_id}/reports` | 按 `source_mode` 查询严格报表 metadata |
| `POST` | `/api/v1/conversations/{conversation_id}/archive` | 幂等归档指定 namespace |
| `DELETE` | `/api/v1/conversations/{conversation_id}` | 删除指定 namespace 及关联 managed HTML |

Conversation API 仅在 SQLite backend 可用；namespace query parameter 必填，page size 为 1–50，cursor 为绑定 endpoint/query/namespace 的 opaque token。完整 request/response schema 以 debug 模式下的 OpenAPI 为准。

## Persistence

- SQLite 默认路径：`local_state/persistence/powerbiagent.db`。
- Report HTML 路径：`local_state/reports/`。
- SQLite 保存结构化状态与 metadata；filesystem 是 HTML 唯一 authority。
- Committed WorkMemory 只从完整 `payload_json` 恢复；缺失、空、损坏、不完整或与 DB integrity columns 冲突时 fail closed，不使用 partial column fallback。
- 只有 terminal Snapshot 可以作为 request replay authority；Memory-without-Snapshot 必须 fail closed。
- Memory conversation API 与 Snapshot/request API 必须显式携带 runtime namespace；Mock/Real 状态严格隔离，history/search 不升级为事实来源。

上述路径均在 Git 之外。当前 schema 由 Alembic 管理；M4.4.2 没有 schema change，也没有新增 migration。

## Development & Validation

```powershell
# Full backend regression
python -m pytest backend/tests -q

# Golden cases
python -m backend.app.harness.cases

# Deterministic governance gates
python scripts/check_architecture_gate.py
python scripts/check_repository_safety.py
python scripts/check_ai_error_ledger.py
python scripts/check_documentation_governance.py

# Fresh SQLite schema smoke
python -m alembic upgrade head
```

`PowerBIAgent Validation` 在 GitHub Actions 上验证 exact commit SHA。CI 只使用 Mock/Fake 边界，不持有 DeepSeek Key、Microsoft Token、PBIX 或真实业务数据；真实 Power BI Desktop 验收始终是本地人工 Smoke。

## Project Status

| Milestone | Status |
|---|---|
| M0–M3 | Sealed |
| M4 | FINAL PASS |
| M4.4.2 | FINAL PASS — truth / persistence boundary final closure |
| M5.0 | FINAL PASS — 前端设计与契约固化 |
| M5.1 | COMPLETE — React 前端实现与核心联调 |
| M5.2 | NOT STARTED — 视觉与交互收口 |

逐版本变更见 [CHANGELOG](CHANGELOG.md)。

## Documentation

- [Project Charter](PROJECT_CHARTER.md) — 项目使命、范围与 North Star。
- [正式 PRD](docs/00_product_requirements_document.md) — 唯一产品需求基线。
- [Development Roadmap](docs/08_development_roadmap.md) — 当前路线与阶段边界。
- [Context Handoff](docs/09_context_handoff.md) — 当前代码状态、限制与下一步。
- [Documentation Map](docs/index.md) — 文档导航与阅读优先级。
- [Architecture Decision Records](docs/adr/) — Accepted ADR 与 authority 边界。
- [AGENTS.md](AGENTS.md) — 代码 Agent 的 Cold Start、Git 与 README maintenance contract。

## Scope / Known Limits

- Local single-machine MVP；不支持多租户、复杂权限或 Power BI RLS。
- Remote MCP Deferred；不承诺生产级远程 Power BI 接入。
- 不支持跨语义模型查询、任意 DAX、任意代码或任意 HTML。
- 当前报表只有 `sales_report`，内容受 runtime capability 与固定安全设计系统约束。
- Real Power BI 验收需要 Windows、Node.js 20+、Power BI Desktop 与本地人工 Smoke；CI 不验证 Desktop 在线链。
- Chat/History 当前没有面向前端的 QueryResult rows、metrics 或 ChartSpec；M5.1 只展示真实文字与 ReportArtifact，不从 answer/execution audit 推导表格或图表。

Proprietary software for internal use.

---

*最后更新：2026-08-21 | M5.1 — React 前端实现与核心联调*
