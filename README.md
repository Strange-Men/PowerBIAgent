# PowerBIAgent

[![PowerBIAgent Validation](https://github.com/Strange-Men/PowerBIAgent/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Strange-Men/PowerBIAgent/actions/workflows/ci.yml?query=branch%3Amain)
![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)

面向 Power BI 语义模型的自然语言分析后端，以确定性事实链提供数据问答、固定模板报表和可恢复的多轮会话。

当前版本：**M5.8.6 — M0-M5 主线发布与治理收口（COMPLETE）**。M5.8.5 correctness 已冻结；main 是合并后新的正式基线。M5.9 = performance / concurrency / resilience / cloud-ready runtime；M5.10 = 第二固定专业报表模板。M5 FINAL=false。

## 项目概览

PowerBIAgent 面向公司内部少量、不熟悉 Power BI 或 DAX 的业务用户。用户用自然语言提出数据问题或报表需求；FastAPI 后端负责语义落地、受限 DAX 构造、Power BI 查询、事实验证、回答与静态 HTML 报表生成。

当前产品形态是 Windows 本地单机 MVP：支持 Mock 离线开发，也支持 DeepSeek 或 Kimi K2.6 + Local MCP + Power BI Desktop 真实链。React 前端通过 Vite 代理接入 FastAPI，并从后端只读目录显式选择 LLM profile 与当前打开的 Desktop/PBIX 模型。

## 核心能力

- 自然语言 Power BI 数据问答，Mock 与 Real 共用同一 TurnPipeline 执行骨架。
- Semantic Grounding 前的 Question Router 区分数据查询、报表、产品帮助、公开模型信息、安全基础算术与不支持的一般问题；非业务 turn 不读取 schema、不执行 DAX、不污染 semantic Memory。
- Power BI MCP runtime schema 是模型结构 authority；immutable `ModelSemanticContext` 把当前 PBIX metadata 适配为候选证据，exact identity + fingerprint 验证的 optional model override 只补充业务语言/temporal metadata，runtime members 继续验证成员值。
- Real DAX 由受限的确定性构造器生成，并在 Power BI 执行前经过独立 Layer 3 验证。
- `VerifiedFactSet` 是数值、结果顺序、筛选、时间与来源信息的唯一对外事实边界。
- Grounding 后的 Semantic Obligation Coverage、StateTransition 后的 Canonical Shape Completeness，以及 QueryResult 到 VerifiedFactSet 前的 Result Semantic Inspection 共同禁止显式条件静默丢失、残缺 shape 执行和错误结果顺序；Answer/Table/Chart 使用确定性 effective scope 与共享展示顺序。
- `sales_report` 是当前唯一“简易模板”，根据用户需求与 runtime capability 生成 KPI、趋势、贡献、对比和排行；报表请求必须显式选择模板，不再存在后端默认模板。
- 结构化多轮 Memory 只补当前轮真正省略的兼容槽；fresh/follow-up/replace 分离，当前明确表达始终优先；歧义、失败、unsupported 和 clarification 不污染已提交状态。
- SQLite 提供重启恢复、结构化历史/搜索、可恢复归档、永久删除、独立 report 删除与崩溃后删除重试。
- `(runtime_mode, conversation_id)` 和 `(source_mode, conversation_id)` 严格隔离 Mock/Real 状态与报表历史。
- `presentation` 只读展示契约把已验证的单指标、表格、柱状图/折线图和报表附件安全交给前端；dataset 只投影 VerifiedFactSet 数据事实覆盖字段，内容块只保存引用。
- 展示型 transcript 与标题支持完整历史恢复、默认标题、重命名、归档和删除，不参与 Memory 或业务事实判断。

## 工作原理

```mermaid
flowchart LR
    User["User"] --> API["FastAPI"]
    API --> Pipeline["TurnPipeline"]
    Pipeline --> Grounding["Intent / Grounding"]
    Grounding --> Coverage["Obligation Coverage"]
    Coverage --> Plan["Canonical QueryPlan"]
    Plan --> Shape["Shape Completeness"]
    Shape --> DAX["Deterministic DAX"]
    DAX --> PBI["Power BI"]
    PBI --> Result["QueryResult"]
    Result --> Inspection["Result Inspection"]
    Inspection --> Facts["VerifiedFactSet"]
    Facts --> Scope["Query Scope / Presentation"]
    Scope --> Output["Answer / Report"]
    Output --> State["Memory / Snapshot"]
```

LLM 负责受约束的语言理解；runtime schema、确定性代码、Power BI、`QueryResult` 与 `VerifiedFactSet` 负责事实真值。Power BI 调用只能经过 `ToolGateway → PowerBIAdapter`，Real 失败不会静默回退 Mock。

## 事实权威边界

| LLM 可以 | LLM 不可以 |
|---|---|
| Intent、turn relation 与受限 `TimeIntentDraft` 语言理解 | 发明业务语义、runtime 对象或 canonical 时间范围 |
| 在 Catalog-owned candidate ID 中进行有界选择 | 生成具有权威性的 Real DAX |
| 生成受事实约束的语言草稿 | 发明 QueryResult、数字、排名、趋势或因果 |
| 输出 registry-owned 报表意图弱信号 | 生成任意 HTML、JavaScript 或报表事实 |

权威来源是 runtime schema、Business Semantic Catalog、确定性 Grounding/StateTransition、Deterministic DAX、Power BI、`QueryResult` 与 `VerifiedFactSet`。SQLite 持久化和历史记录不是业务事实来源。

## 当前能力

| 领域 | 已实现能力 |
|---|---|
| 数据问答 | SCALAR、dimension-only ENTITY_LIST、GROUPED、RANKING/Top1、runtime-validated MEMBER_SET/`IN_SET`、FILTERED_AGGREGATION、TREND 与 BOUNDED_TREND；只澄清当前 shape 真正缺失的槽位 |
| 非业务路由 | code-owned 产品能力说明、公开 LLM profile 信息、安全 Decimal 基础算术与明确 unsupported；ZERO schema/member/DAX/semantic Memory mutation |
| 报表 | 唯一正式“简易模板” `sales_report`；显式 `report_template_key` 必选；schema-aware capability planning；固定安全静态 HTML；查看/下载资源 |
| 多轮 Memory | 当前明确表达 > bounded semantic draft > committed Memory；fresh 清除无关旧槽，follow-up/replace 只继承兼容省略项；模型切换清空旧语义上下文 |
| 持久化与恢复 | SQLite Memory/Snapshot/报表 metadata；重启重放；不完整崩溃证据受控失败；持久化删除意图 |
| 历史与搜索 | 仅 SQLite 支持最近会话、展示型 transcript、自动标题/重命名、有界搜索、archive/restore 与永久删除；旧会话只恢复真实已保存内容 |
| 多模型 LLM | DeepSeek 与 Kimi K2.6 共享 OpenAI-compatible Provider；每轮按公开 profile key 冻结 provider/model snapshot，无全局 mutable default、自动路由或失败 fallback |
| 本地 Power BI | DeepSeek/Kimi + 只读 Local Modeling MCP + Power BI Desktop；可同时安全枚举多个 PBIX，由前端单选后使用 opaque key 精确绑定；每次 schema/member/DAX 都重新枚举并只连接唯一匹配实例，stale/ambiguous identity fail closed；Real DAX/事实的 LLM 权限为 0 |
| React 网页前端 | 完整历史恢复、已归档入口/恢复、独立 report 删除、A/B history stale-response 防护，以及文字/指标/表格/柱状图/折线图/报表附件动态渲染 |

Local MCP 实机基线固定为 `@microsoft/powerbi-modeling-mcp@0.5.0-beta.12`，并通过只读 schema + DAX 单行 capability probe 校验协议能力。Remote MCP 继续延期。M5.3.3 不改变 M0–M5 factual authority。

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
LLM_DEFAULT_PROFILE=deepseek
POWERBI_MODE=local_mcp
PERSISTENCE_BACKEND=sqlite
MAX_TOOL_CALLS=8
POWERBI_LOCAL_MCP_READONLY=true
DEEPSEEK_API_KEY=<用户自己的 Key>
```

按以下顺序启动：

1. 在 Power BI Desktop 中打开一个或多个目标 PBIX。
2. 启动 FastAPI 后端。
3. 启动 React 前端。
4. 打开 `http://127.0.0.1:5173`。
5. 在“数据模型”菜单确认显示当前 Desktop 模型列表，而不是 Mock 模型；选择本轮要分析的 PBIX。
6. 在“AI 模型”菜单显式选择 DeepSeek 或已配置的 Kimi K2.6；提交后该轮 profile 不再受后续 UI 切换影响。

Kimi K2.6 使用用户自有的 OpenAI-compatible gateway；生产代码不提供真实 host 或 Key。启用时设置 `LLM_MODE=openai_compatible`、`LLM_DEFAULT_PROFILE=kimi-k2.6`、`KIMI_BASE_URL=<用户 gateway>/v1`、`KIMI_API_KEY=<用户 Key>` 与 `KIMI_MODEL=azure/Kimi-K2.6`。也可同时配置 DeepSeek/Kimi，由前端逐轮显式选择；任一 provider 失败均不会自动切换到另一 provider。

`PERSISTENCE_BACKEND=sqlite` 是最近会话、搜索、历史和报表历史正常工作的前提。启动后可执行以下只读检查：

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/api/v1/semantic-models
```

正常 Real catalog 的 `runtime_mode` 应为 `real`，每个模型的 `source` 应为 `local_desktop`，而不是 `mock`。后端为每个 Desktop 实例确定性生成当前进程内的 `local_desktop:<opaque-id>`；它不暴露 PID、端口、connection string 或 raw fingerprint，display name 只用于展示。`/health` 只验证当前 runtime 配置是否就绪，不探测 Power BI Desktop 是否在线；实际模型连接状态以 `/api/v1/semantic-models` 为准。compatibility probe 会针对每个精确 option 验证 protocol、required tools、Connect、schema 读取与 `EVALUATE ROW("__pbiagent_probe", 1)` 的一行结果。Desktop 或后端进程重启后旧 key 可失效，前端刷新目录并要求重新选择，不自动切换到其他 PBIX。

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

#### `python-dotenv could not parse statement starting at line ...`

`.env` 只能包含 `KEY=value`、以 `#` 开头的注释和空行。不要粘贴 Markdown 代码围栏、PowerShell 命令、项目符号或只有 `KEY` 没有 `=` 的内容；一个配置项只占一行。诊断命令只报告非法行号与安全配置状态，不打印任何配置值或 Key：

```powershell
python scripts/check_startup_config.py --env-file .env
```

按报告行号在本地修正后重新运行诊断，再重启后端。不要把 `.env`、诊断时使用的真实 Key 或任何 Secret 提交到 Git。

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

Local MCP DAX 执行会验证实际 columns/rows/`rowCount` shape，并使用一行 sentinel 探测上限。协议显式返回的 truncation/limit metadata 会映射到 `QueryResult.truncated`；beta.12 无法证明完整且结果触及请求上限时保守标记 truncated，`VerifiedFactSet` 不会据此宣称全量排名、最大值或最小值完整。

## 运行模式

| `LLM_MODE` | `POWERBI_MODE` | 用途 |
|---|---|---|
| `mock` | `mock` | 默认离线开发与 CI，不需要 Secret |
| `deepseek` | `mock` | 真实语言模型 + Mock Power BI 数据 |
| `deepseek` | `local_mcp` | 真实 DeepSeek + readonly Local MCP + Power BI Desktop |
| `openai_compatible` | `local_mcp` | DeepSeek/Kimi profile 目录 + readonly Local MCP；默认 profile 由 `LLM_DEFAULT_PROFILE` 指定 |

`remote_mcp` 当前不可用。`PERSISTENCE_BACKEND=memory` 是兼容性默认值，只保留进程内状态；需要重启恢复、历史或搜索时必须显式使用 `PERSISTENCE_BACKEND=sqlite`。

## API 接口

| 方法 | 路径/字段 | 说明 |
|---|---|---|
| `GET` | `/health` | 当前 runtime 配置就绪状态 |
| `GET` | `/api/v1/semantic-models` | 当前 Desktop 模型的安全目录、runtime namespace 与最小 Agent compatibility 状态 |
| `GET` | `/api/v1/report-templates` | 当前可用的 registry-owned 报表模板只读目录；前端不维护第二份模板 authority |
| `GET` | `/api/v1/llm-profiles` | 安全公开的 LLM profile 目录；不返回 Key 或 base URL |
| `POST` | `/api/v1/chat` | 非流式数据问答与报表生成 |
| 字段 | `semantic_model_key` | 从发现目录选择 opaque 模型 key；必须精确绑定当前 Desktop 实例 |
| 字段 | `llm_profile_key` | 本轮显式选择的公开 LLM profile；进入幂等指纹并在 turn 内冻结 |
| 字段 | `report_template_key` | 报表请求必须显式提供的 registry-owned 模板 key；当前仅 `sales_report`（“简易模板”），missing/invalid/stale 均在 ReportSpec/Renderer/artifact 前 fail closed |
| `GET` | `/api/reports/{report_id}` | 查看 repository-owned HTML 报表 |
| `GET` | `/api/reports/{report_id}/download` | 下载 UTF-8 HTML 报表 |
| `GET` | `/api/v1/conversations` | 按 `runtime_mode` 查询最近会话 |
| `GET` | `/api/v1/conversations/search` | 按 `runtime_mode` 搜索声明范围内的持久化字段 |
| `GET` | `/api/v1/conversations/{conversation_id}/history` | 持久化的展示型 user/assistant transcript 与结构化轮次结果；不成为事实来源 |
| `GET` | `/api/v1/conversations/{conversation_id}/reports` | 按 `source_mode` 查询严格报表 metadata |
| `PATCH` | `/api/v1/conversations/{conversation_id}` | 在 `runtime_mode` namespace 内重命名会话；只修改 presentation metadata |
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
- conversation `title`、Snapshot `user_message` 和 `presentation` 只服务 UI 恢复；它们不能输入 Grounding、QueryPlan、Memory 或 VerifiedFactSet。

上述路径均在 Git 之外。当前 schema 由 Alembic 管理；M5.3 migration 仅为 `conversations` 增加 nullable `title` presentation metadata，不改变 conversation identity、Memory 或事实链。

## 开发与验证

```powershell
# 后端完整回归
python -m pytest backend/tests -q

# 永久语义兼容门禁
python scripts/check_semantic_compatibility.py

# Golden 用例
python -m backend.app.harness.cases

# 确定性治理门禁
python scripts/check_architecture_gate.py
python scripts/check_repository_safety.py
python scripts/check_ai_error_ledger.py
python scripts/check_documentation_governance.py
python scripts/check_artifact_governance.py

# 全新 SQLite schema Smoke
python -m alembic upgrade head
```

`PowerBIAgent Validation` 在 GitHub Actions 上验证准确的 commit SHA，并由 `main` / `m5/rebuild` 的 push 或 pull request 触发。Semantic Compatibility Gate 扫描完整 `backend/app/**` production 文本并禁止依赖 known-answer/test oracle，且在 full pytest 前运行；同一 workflow 使用 Node.js LTS 与 `npm ci` 执行 frontend Vitest、typecheck、lint 和 production build。CI 只使用 Mock/Fake 边界，不持有 DeepSeek Key、Microsoft Token、PBIX 或真实业务数据；真实 Power BI Desktop 验收始终是本地人工 Smoke。

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
| M5.3 | 已完成 — 结构化结果、历史/标题/管理、响应式与视觉交互已收口；Rich PBIX Real 验收通过 |
| M5.3.1 | 已完成 — 多 Desktop 实例连接前 fail closed；presentation 仅投影 verified 数据字段 |
| M5.3.2 | 已完成 — 多 PBIX 安全枚举/单选/opaque 精确绑定、MCP capability probe、stale 与 truncation 防腐 |
| M5.3.3 | 已完成 — 多轮继承语义、unsupported preflight、archive/restore、独立 report delete、A/B 防串窗与 Artifact Governance |
| M5.4 | 已完成 — conversation-scoped state、client UUID pending session、异会话并发、用户卡片/资源管理、report tombstone/rename |
| M5.4.1 | 已完成 — Settings 独立全量分页、准确 selection/batch 语义与 automation-owned resource cleanup |
| M5.4.2 | 已完成 — 从 M5.4.1 `cab40b0` 建立重建线并固化分阶段开发与泛化验收；无生产功能变化 |
| M5.5 | COMPLETE — Semantic correctness、runtime member、multi-turn、TopN、time 与 capability boundary |
| M5.6 | COMPLETE — Presentation/Localization/Resource UX truth；共享 floating menu 与 Settings nested-scroll/action 可达性 |
| M5.7 | COMPLETE — 简易报表视觉、响应式可读性、显式模板必选与人工视觉验收 |
| M5.7.1 | COMPLETE — 统一语义可靠性、回归防火墙与高强度问答验收 |
| M5.7.2 | COMPLETE — Report Template Gate 前移、Template/Renderer Registry、后端目录驱动的前端模板选择，以及简易模板视觉与信息架构最终收口 |
| M5.8 | COMPLETE — OpenAI-compatible LLM Provider、DeepSeek/Kimi-K2.6 与 request/conversation-scoped model selection |
| M5.8.1 | COMPLETE — 前置性能加速、Local MCP session reuse 与安全进程内 metadata/member cache |
| M5.8.2 | COMPLETE — Question Router、通用 Query Shape、minimal clarification、dimension-only/Top1/member-set/bounded trend 与安全 calculator/help/system-info |
| M5.8.3 | runtime metadata → immutable ModelSemanticContext → SemanticCatalog；COMPLETE（b86662e / CI success） |
| M5.8.4 | COMPLETE；同一 runtime Catalog 内的跨语言对象/成员绑定与多轮保持；`3e3d8ac` / CI #46 exact-SHA completed/success |
| M5.8.5 | COMPLETE；Semantic Coverage、Shape Completeness、Result Inspection、Query Scope/ordering 四个通用 invariant |
| M5.8.6 | COMPLETE — M0-M5 主线发布与治理收口；main 已合并为新的正式基线；m5/frontend 已归档 |
| M5.9 | NOT STARTED — 完整 MCP performance、resilience、并发与压力验证 |
| M5.10 | NOT STARTED — 固定专业销售模板与“简易模板/销售模板”显式选择；只有全部门禁完成后才允许 M5 FINAL |

逐版本变更见 [变更记录](CHANGELOG.md)。

## 文档导航

- [项目章程](PROJECT_CHARTER.md) — 项目使命、范围与北极星。
- [正式 PRD](docs/00_product_requirements_document.md) — 唯一产品需求基线。
- [开发路线](docs/08_development_roadmap.md) — 当前路线与阶段边界。
- [上下文交接](docs/09_context_handoff.md) — 当前代码状态、限制与下一步。
- [文档地图](docs/index.md) — 文档导航与阅读优先级。
- [架构决策记录](docs/adr/) — 已接受的 ADR 与权威边界。
- [M5 泛化与验收契约](docs/specs/13_m5_generalization_and_acceptance_contract.md) — 重建历史、M5.5—M5.10 边界与 Generalization Gate。
- [AGENTS.md](AGENTS.md) — 代码 Agent 的 Cold Start、Git 与 README 维护约定。

## 范围与已知限制

- 本地单机 MVP；不支持多租户、复杂权限或 Power BI RLS。
- Remote MCP 延期；不承诺生产级远程 Power BI 接入。
- 不支持跨语义模型查询、任意 DAX、任意代码或任意 HTML。
- 当前报表只有“简易模板” `sales_report`，内容受 runtime capability 与固定安全设计系统约束；报表请求必须显式选择模板。
- Real Power BI 验收需要 Windows、Node.js 20+、Power BI Desktop 与本地人工 Smoke；CI 不验证 Desktop 在线链。
- 当前结构化展示支持单值指标、多行表格，以及根据真实 QueryResult 字段引用生成的简单柱状图或折线图；不提供前端排序/筛选工作台、任意 ChartSpec 或前端推断数据。
- `m5/rebuild` 已冻结为只读发布追溯分支，不接收 M5.9/M5.10 新开发。`m5/frontend` 上的 `a197db3`（原 M5.5）与 `6d1620a`（原 M5.5.1）作为实验/审计历史由 `archive/m5-frontend-experimental-final` tag 永久保存；新线从 M5.4.1 `cab40b0` 重新开始，能力必须分阶段重新实现并重新验收。main 是唯一活动开发线。

公司内部专有软件。

---

*最后更新：2026-09-03 | M5.8.6 COMPLETE（主线发布与治理收口）；M5.9 / M5.10 NOT STARTED；M5 FINAL=false*
