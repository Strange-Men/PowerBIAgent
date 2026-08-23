# PowerBIAgent

[![PowerBIAgent Validation](https://github.com/Strange-Men/PowerBIAgent/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Strange-Men/PowerBIAgent/actions/workflows/ci.yml)
![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)

面向 Power BI 语义模型的自然语言分析后端，以确定性事实链提供数据问答、固定模板报表和可恢复的多轮会话。

当前版本：**M5.2.1 — 模型能力边界与真实模式说明收口**。M4.4.2 已最终验收；M5.0/M5.1/M5.2/M5.2.1 已完成；M5.3 尚未开始。

## 项目概览

PowerBIAgent 面向公司内部少量、不熟悉 Power BI 或 DAX 的业务用户。用户用自然语言提出数据问题或报表需求；FastAPI 后端负责语义落地、受限 DAX 构造、Power BI 查询、事实验证、回答与静态 HTML 报表生成。

当前产品形态是 Windows 本地单机 MVP：支持 Mock 离线开发，也支持 DeepSeek + Local MCP + Power BI Desktop 真实链。React 前端通过 Vite 代理接入 FastAPI，并从后端只读发现接口动态选择当前 Desktop 模型。

## 核心能力

- 自然语言 Power BI 数据问答，Mock 与 Real 共用同一 TurnPipeline 执行骨架。
- Business Semantic Grounding 将用户表达绑定到 runtime schema、模型专属 glossary 与 runtime members。
- Real DAX 由受限的确定性构造器生成，并在 Power BI 执行前经过独立 Layer 3 验证。
- `VerifiedFactSet` 是数值、结果顺序、筛选、时间与来源信息的唯一对外事实边界。
- `sales_report` 根据用户需求与 runtime capability 生成 KPI、趋势、贡献、对比和排行等固定设计报表。
- 结构化多轮 Memory 只在完整成功后提交；歧义、失败和 clarification 不污染已提交状态。
- SQLite 提供重启恢复、结构化历史/搜索/归档/删除与崩溃后删除重试。
- `(runtime_mode, conversation_id)` 和 `(source_mode, conversation_id)` 严格隔离 Mock/Real 状态与报表历史。

## 工作原理

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

## 事实权威边界

| LLM 可以 | LLM 不可以 |
|---|---|
| Intent 与受约束语言理解 | 发明业务语义或 runtime 对象 |
| 在 Catalog-owned candidate ID 中进行有界选择 | 生成具有权威性的 Real DAX |
| 生成受事实约束的语言草稿 | 发明 QueryResult、数字、排名、趋势或因果 |
| 输出 registry-owned 报表意图弱信号 | 生成任意 HTML、JavaScript 或报表事实 |

权威来源是 runtime schema、Business Semantic Catalog、确定性 Grounding/StateTransition、Deterministic DAX、Power BI、`QueryResult` 与 `VerifiedFactSet`。SQLite 持久化和历史记录不是业务事实来源。

## 当前能力

| 领域 | 已实现能力 |
|---|---|
| 数据问答 | Measure、Dimension、`EQ` filter、确定性时间范围、单 Measure Sort/TopN 的受限自然语言查询 |
| 报表 | 唯一正式模板 `sales_report`；schema-aware capability planning；固定安全静态 HTML；查看/下载资源 |
| 多轮 Memory | 指标、维度、filter、time、sort、TopN 继承；待澄清上下文与已提交 Memory 分离；损坏的 canonical filter 受控失败 |
| 持久化与恢复 | SQLite Memory/Snapshot/报表 metadata；重启重放；不完整崩溃证据受控失败；持久化删除意图 |
| 历史与搜索 | 仅 SQLite 支持最近会话、结构化历史、有界搜索、归档和删除；不伪造逐字记录 |
| 本地 Power BI | DeepSeek + 只读 Local Modeling MCP + Power BI Desktop；Real DAX/事实的 LLM 权限为 0 |
| React 网页前端 | GPT 式对话页面、可折叠 Sidebar、Desktop 模型动态发现、可选模板 override、Chat/History/Search/Reports 联调与用户可理解的终态渲染 |

Remote MCP 继续延期。M5.2.1 已完成模型能力边界与真实模式说明收口；M5.3 视觉与交互最终收口尚未开始。

## 快速开始

> **默认配置是 Mock，只用于开发测试。** 要查询当前打开的真实 PBIX，请先按“本地 Power BI 真实模式启动”配置本地 `.env`，再启动后端和前端。

### 环境要求

- Windows 本地环境。
- Python 3.11；仓库固定 Conda 环境名为 `PBIAgent`（Conda 安装于 `D:\Conda`）。
- Mock 后端不需要 API Key 或 Power BI Desktop；运行 React 前端需要 Node.js 20.19+。
- Real Local MCP 需要 Node.js 20+、npm/npx、Power BI Desktop，以及已打开的目标 PBIX。

### 本地 Power BI 真实模式启动

仓库默认配置是 Mock，只用于离线开发和测试。如果前端出现以下任一内容，说明当前**不是 Real 模式**：

- “Mock 销售模型”；
- `mock_*` 模型 key；
- 固定的假回答。

Real 模式至少需要在本地 `.env` 中配置以下内容；`DEEPSEEK_API_KEY` 只填写用户自己的 Key，不得提交、输出或记录：

```dotenv
LLM_MODE=deepseek
POWERBI_MODE=local_mcp
PERSISTENCE_BACKEND=sqlite
MAX_TOOL_CALLS=8
POWERBI_LOCAL_MCP_READONLY=true
DEEPSEEK_API_KEY=<用户自己的 Key>
```

按以下顺序启动：

1. 在 Power BI Desktop 中打开目标 PBIX。
2. 启动 FastAPI 后端。
3. 启动 React 前端。
4. 打开 `http://127.0.0.1:5173`。
5. 在“数据模型”菜单确认显示当前 Desktop 模型，而不是 Mock 模型。

`PERSISTENCE_BACKEND=sqlite` 是最近会话、搜索、历史和报表历史正常工作的前提。启动后可执行以下只读检查：

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/api/v1/semantic-models
```

正常 Real catalog 的 `runtime_mode` 应为 `real`，模型的 `source` 应为 `local_desktop`，而不是 `mock`。`/health` 只验证当前 runtime 配置是否就绪，不探测 Power BI Desktop 是否在线；实际模型连接状态以 `/api/v1/semantic-models` 为准。

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

### 安装

```powershell
D:\Conda\Scripts\conda.exe env create -f environment.yml
D:\Conda\envs\PBIAgent\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
conda activate PBIAgent
```

`.env.example` 是唯一可提交的配置模板。Mock 默认配置可直接运行；真实 Secret 只由用户写入本地 `.env`，不得提交或输出。

### 启动

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

打开 `http://127.0.0.1:5173`。Vite 开发服务器将 `/api` 与 `/health` 代理到 `127.0.0.1:8000`。SQLite 历史和搜索功能需要后端设置 `PERSISTENCE_BACKEND=sqlite`；前端最终使用的 runtime namespace 以后端发现结果为准。

```powershell
curl.exe http://127.0.0.1:8000/health

curl.exe -X POST http://127.0.0.1:8000/api/v1/chat `
  -H "Content-Type: application/json" `
  -d '{"message":"本月销售额是多少？"}'
```

`DEBUG=true` 时可访问 `http://127.0.0.1:8000/docs`；关闭 debug 后不暴露 Swagger/ReDoc。

### 常见启动问题

#### `No module named uvicorn`

使用 `python -m uvicorn ...` 时报错，但 `conda run -n PBIAgent python -m uvicorn ...` 正常。
**原因：** PowerShell 的 `conda activate` 未生效，Python 仍指向 base 环境（`D:\Conda\python.exe`）。
**解决：** 执行 `conda init powershell` 一次 → 关闭并重新打开 PowerShell → 确认 `python -c "import sys; print(sys.executable)"` 输出 `D:\Conda\envs\PBIAgent\python.exe`。

作为一次性临时方案，也可用绝对路径直接启动：

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

如果输出是 `D:\Conda\python.exe`，说明环境激活未生效，参照上一条执行 `conda init powershell`。

`sales_report` 的 schema、4 次查询和渲染需要 `MAX_TOOL_CALLS=8` 的正式工具预算；更低值会受控失败。仓库固定实机基线为 `@microsoft/powerbi-modeling-mcp@0.5.0-beta.12`；详细前置条件、Smoke 与故障分类见 [Power BI MCP 与 API 契约](docs/04_powerbi_mcp_and_api_contracts.md) 和 [M2 集成计划](docs/milestones/m2/12_m2_powerbi_mcp_integration_plan.md)。

## 运行模式

| `LLM_MODE` | `POWERBI_MODE` | 用途 |
|---|---|---|
| `mock` | `mock` | 默认离线开发与 CI，不需要 Secret |
| `deepseek` | `mock` | 真实语言模型 + Mock Power BI 数据 |
| `deepseek` | `local_mcp` | 真实 DeepSeek + readonly Local MCP + Power BI Desktop |

`remote_mcp` 当前不可用。`PERSISTENCE_BACKEND=memory` 是兼容性默认值，只保留进程内状态；需要重启恢复、历史或搜索时必须显式使用 `PERSISTENCE_BACKEND=sqlite`。

## API 接口

| 方法 | 路径/字段 | 说明 |
|---|---|---|
| `GET` | `/health` | 当前 runtime 配置就绪状态 |
| `GET` | `/api/v1/semantic-models` | 当前后端可连接且可进入正式 Chat pipeline 的安全模型目录与 runtime namespace |
| `POST` | `/api/v1/chat` | 非流式数据问答与报表生成 |
| 字段 | `semantic_model_key` | 从发现目录选择语义模型 |
| 字段 | `report_template_key` | 可选的显式模板 override；未传不等于禁用报表 |
| `GET` | `/api/reports/{report_id}` | 查看 repository-owned HTML 报表 |
| `GET` | `/api/reports/{report_id}/download` | 下载 UTF-8 HTML 报表 |
| `GET` | `/api/v1/conversations` | 按 `runtime_mode` 查询最近会话 |
| `GET` | `/api/v1/conversations/search` | 按 `runtime_mode` 搜索声明范围内的持久化字段 |
| `GET` | `/api/v1/conversations/{conversation_id}/history` | 持久化的结构化轮次历史，不是逐字记录 |
| `GET` | `/api/v1/conversations/{conversation_id}/reports` | 按 `source_mode` 查询严格报表 metadata |
| `POST` | `/api/v1/conversations/{conversation_id}/archive` | 幂等归档指定 namespace |
| `DELETE` | `/api/v1/conversations/{conversation_id}` | 删除指定 namespace 及关联的受管 HTML |

Conversation API 仅在 SQLite 后端可用；namespace 查询参数必填，每页数量为 1–50，cursor 是绑定端点、查询与 namespace 的不透明令牌。完整请求/响应 schema 以 debug 模式下的 OpenAPI 为准。

## 持久化

- SQLite 默认路径：`local_state/persistence/powerbiagent.db`。
- Report HTML 路径：`local_state/reports/`。
- SQLite 保存结构化状态与 metadata；文件系统是 HTML 的唯一权威来源。
- 已提交 WorkMemory 只从完整 `payload_json` 恢复；缺失、空、损坏、不完整或与数据库完整性列冲突时受控失败，不使用部分列回退。
- 只有终态 Snapshot 可以作为请求重放权威；存在 Memory 但缺少 Snapshot 时必须受控失败。
- Memory conversation API 与 Snapshot/request API 必须显式携带 runtime namespace；Mock/Real 状态严格隔离，历史和搜索不会升级为事实来源。

上述路径均在 Git 之外。当前 schema 由 Alembic 管理；M5.2.1 没有 schema 变更，也没有新增 migration。

## 开发与验证

```powershell
# 后端完整回归
python -m pytest backend/tests -q

# Golden 用例
python -m backend.app.harness.cases

# 确定性治理门禁
python scripts/check_architecture_gate.py
python scripts/check_repository_safety.py
python scripts/check_ai_error_ledger.py
python scripts/check_documentation_governance.py

# 全新 SQLite schema Smoke
python -m alembic upgrade head
```

`PowerBIAgent Validation` 在 GitHub Actions 上验证准确的 commit SHA。CI 只使用 Mock/Fake 边界，不持有 DeepSeek Key、Microsoft Token、PBIX 或真实业务数据；真实 Power BI Desktop 验收始终是本地人工 Smoke。

## 项目状态

| 里程碑 | 状态 |
|---|---|
| M0–M3 | 已封板 |
| M4 | 已最终验收 |
| M4.4.2 | 已最终验收 — 事实与持久化边界最终收口 |
| M5.0 | 已完成 — 前端设计与契约固化 |
| M5.1 | 已完成 — React 前端实现与核心联调 |
| M5.2 | 已完成 — 真实业务链路与前端逻辑收口 |
| M5.2.1 | 已完成 — 模型能力边界与真实模式说明收口 |
| M5.3 | 尚未开始 — 视觉与交互最终收口 |

逐版本变更见 [变更记录](CHANGELOG.md)。

## 文档导航

- [项目章程](PROJECT_CHARTER.md) — 项目使命、范围与北极星。
- [正式 PRD](docs/00_product_requirements_document.md) — 唯一产品需求基线。
- [开发路线](docs/08_development_roadmap.md) — 当前路线与阶段边界。
- [上下文交接](docs/09_context_handoff.md) — 当前代码状态、限制与下一步。
- [文档地图](docs/index.md) — 文档导航与阅读优先级。
- [架构决策记录](docs/adr/) — 已接受的 ADR 与权威边界。
- [AGENTS.md](AGENTS.md) — 代码 Agent 的 Cold Start、Git 与 README 维护约定。

## 范围与已知限制

- 本地单机 MVP；不支持多租户、复杂权限或 Power BI RLS。
- Remote MCP 延期；不承诺生产级远程 Power BI 接入。
- 不支持跨语义模型查询、任意 DAX、任意代码或任意 HTML。
- 当前报表只有 `sales_report`，内容受 runtime capability 与固定安全设计系统约束。
- Real Power BI 验收需要 Windows、Node.js 20+、Power BI Desktop 与本地人工 Smoke；CI 不验证 Desktop 在线链。
- Chat/History 当前没有面向前端的 QueryResult rows、metrics 或 ChartSpec；当前只展示真实文字与 ReportArtifact，不从 answer/execution audit 推导表格或图表。结构化表格/图表契约必须在 M5.3 前另行补充。

公司内部专有软件。

---

*最后更新：2026-08-23 | M5.2.1 — 模型能力边界与真实模式说明收口完成*
