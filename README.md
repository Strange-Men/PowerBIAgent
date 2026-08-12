# PowerBIAgent — Power BI 数据分析 Agent MVP

## 项目简介

PowerBIAgent 是供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。

核心链路：用户自然语言提问 → React 极简对话页面 → FastAPI 后端 → 确定性 TurnPipeline 编排（意图识别 → QueryPlan → DAX → Answer → ReportSpec）→ DeepSeek（受控结构化 LLM 调用）→ Power BI MCP → Power BI 语义模型 → 数据问答或固定模板静态 HTML 报表。

## 当前状态

**M2.6.1 Known-answer 独立数值 Oracle 与多轮 Harness/Test Set 离线固化完成。**

> M0—M1 已正式封板，M2 Local Demo 已由固定 Tag `m2-local-powerbi-demo-release` 封板。M2.6.1 在 Harness/Test 边界建立独立数值 Oracle、8 个 Known-answer Case（2 个 holdout）与 6 组/15 Turn 多轮 MiniSuite，并完成 Fake/Mock 离线验收。真实 expected baseline 仅允许保存在 Git 忽略的 `local_state/`。本轮未调用 DeepSeek、Local MCP 或 Desktop；M2.6.2 最终真实数值与多轮验收尚未执行，Remote MCP 继续 Deferred。

### 幂等与并发特性

- **相同 request_id + 相同请求**：幂等重放，不重复执行 LLM/工具/Memory
- **相同 request_id + 不同请求**：HTTP 409 `request_id_conflict`
- **并发相同 request_id**：仅一个请求执行（Owner），其余等待重放（Waiter）
- **并发不同 request_id**：正常独立执行

> **限制：** 当前快照和并发防重仅保证单进程 Service 实例。分布式幂等将在后续基础设施阶段处理。

## 开发环境准备

### Conda 环境

本机 Conda 安装目录：`D:\Conda`

#### 检查 Conda

```powershell
D:\Conda\Scripts\conda.exe --version
```

#### 创建 PBIAgent 环境

```powershell
D:\Conda\Scripts\conda.exe create -n PBIAgent python=3.11 -y
```

#### 激活 PBIAgent 环境

```powershell
# 推荐：直接使用环境中的 Python
D:\Conda\envs\PBIAgent\python.exe --version
```

#### 安装项目依赖

```powershell
# 仅安装运行依赖
D:\Conda\envs\PBIAgent\python.exe -m pip install -e .

# 安装开发和测试依赖
D:\Conda\envs\PBIAgent\python.exe -m pip install -e ".[dev]"
```

核心依赖：FastAPI、Uvicorn、pydantic-settings、httpx、官方 MCP Python SDK（版本已锁定，见 pyproject.toml）。

### M2 Local MCP 外部前置

- Windows 与 Power BI Desktop；运行 Smoke 前需打开一个测试 PBIX。
- Node.js 20+（包含 npm / npx）。
- Local Server 的 M2.1—M2.5 实机验证固定版本为 `@microsoft/powerbi-modeling-mcp@0.5.0-beta.12`，项目以 stdio 和 `--readonly` 启动。
- Local Demo 不要求 Tenant ID、Client ID、Redirect URI 或 Microsoft Token。

### 环境变量

项目使用 `.env` 文件和环境变量配置。Mock 模式启动不需要任何 API Key。

#### 创建本地 .env

```powershell
Copy-Item .env.example .env
```

然后：
- `.env` 由用户本人本地填写真实 API Key
- `.env` 禁止提交（已在 `.gitignore` 中排除）
- Claude / Codex / 其他代码 Agent 和自动化工具不得读取 `.env` 内容
- DeepSeek API Key 只在后端运行时使用
- 前端永远不保存模型 API Key

#### 环境变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_ENV` | `development` | 运行环境 (development/test/production) |
| `LLM_MODE` | `mock` | LLM 模式 (mock/deepseek) |
| `POWERBI_MODE` | `mock` | Power BI 模式 (mock/local_mcp/remote_mcp)；Local 可接现有 Chat，Remote 仍不可用 |
| `POWERBI_LOCAL_SEMANTIC_MODEL_KEY` | `local_desktop_model` | Local Desktop 模型的 friendly key；不接受端口或连接串 |
| `HOST` | `127.0.0.1` | 监听地址 |
| `PORT` | `8000` | 监听端口 |

### 启动应用

```powershell
D:\Conda\envs\PBIAgent\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

### 健康检查

```powershell
curl http://127.0.0.1:8000/health
```

响应示例：

```json
{
  "status": "ok",
  "ready": true,
  "configuration_ready": true,
  "powerbi_live_connected": false,
  "reasons": [],
  "app_name": "PowerBIAgent",
  "app_env": "development",
  "version": "M2.6.1",
  "llm_mode": "mock",
  "powerbi_mode": "mock",
  "harness_mode": "strict",
  "timestamp": "2026-07-31T07:03:23Z"
}
```

`ready` 为兼容字段，等同 `configuration_ready`；两者只说明配置可创建当前运行模式，不代表 Power BI Desktop 此刻实时连接正常。真实连接仍由实际 Turn 或人工 Smoke 验证。

### M2.1 Local MCP 人工 Smoke

先在 Power BI Desktop 打开测试 PBIX，再运行：

```powershell
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\powerbi_local_mcp_connection_smoke.py
```

Smoke 只做协议、工具发现与 Desktop 连接，不读取完整 Schema、不执行 DAX、不调用 DeepSeek。

### M2.2 Local MCP Schema 人工 Smoke

先在 Power BI Desktop 打开本地测试 PBIX，再运行：

```powershell
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\powerbi_local_mcp_schema_smoke.py
```

Smoke 经 ToolGateway → LocalMCPPowerBIAdapter 读取真实 Schema，只输出脱敏计数与固定预期字段检查；不打印完整 Schema、Measure expression、连接信息或业务数据，不执行 DAX，不调用 DeepSeek。

### M2.3 Local MCP DAX 人工 Smoke

先在 Power BI Desktop 打开本地测试 PBIX，再运行：

```powershell
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\powerbi_local_mcp_dax_smoke.py
```

Smoke 经 ToolGateway → LocalMCPPowerBIAdapter 执行固定 `ROW` 与两个 Demo Measure 查询，只输出行数、固定值校验和 `source_mode` 标志；不打印连接信息、原始 MCP 响应或业务数值，不调用 DeepSeek。

### M2.4 DeepSeek + Local Power BI Chat 人工 Smoke

先在 Power BI Desktop 打开本地测试 PBIX，并在本地 `.env` 配置 DeepSeek，再运行：

```powershell
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\deepseek_local_powerbi_chat_smoke.py
```

Smoke 复用正式 API、DeepSeekTurnService、TurnPipeline 与 ToolGateway，验证总销售额、总数量和带类别筛选的销售额三个真实 Case；输出经过脱敏，不打印 DAX、业务值、连接信息或 Secret。本地临时 Trace 位于系统临时目录，不进入 Git。

### M2.5 Business Golden 人工 Smoke

先在 Power BI Desktop 打开本地测试 PBIX，并在本地 `.env` 配置 DeepSeek，再运行：

```powershell
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\m2_business_golden_smoke.py
```

Smoke 通过正式 Chat API 验证 7 个真实业务 Case，覆盖 Measure、Dimension、Filter、Top N/Sort 与 Schema 泛化；输出仅包含 Case 成败、契约匹配、Layer 3、source mode、Answer provenance 和调用/修复计数，不打印 DAX、业务数值、Prompt、原始响应、连接信息或 PBIX 路径。`gc_012_real_baseline` 由该人工 Smoke 提供真实基线，通用 CI 仍只运行 Mock/Fake。

### M2.6.1 Known-answer / Multi-turn 离线 Harness

```powershell
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\m2_known_answer_multiturn_smoke.py --mode offline
```

该 Runner 复用正式 `create_app → /api/v1/chat` 路径，以 Fake/Mock 虚构数据验证 8 个 Known-answer Case、2 个 holdout 及 6 组/15 Turn Conversation。`--mode real` 在 M2.6.1 只校验 `local_state/m2_known_answers.yaml` 是否存在且覆盖完整，始终不执行真实调用；真实执行仅属于 M2.6.2。真实数值不得提交、推送或写入公开 fixture/Trace。

### 对话接口

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "本月销售额是多少？"}'
```

响应示例：

```json
{
  "request_id": "...",
  "conversation_id": "...",
  "terminal_state": "completed",
  "intent": "data_question",
  "response_type": "answer",
  "answer": "本月销售额约为 1,250 万元，较上月增长 8.3%...",
  "tool_sequence": ["get_semantic_model_schema", "execute_dax"],
  "memory_commit": true,
  "trace_id": "...",
  "is_mock": true,
  "idempotent_replay": false,
  "replayed_request_id": null
}
```

### 运行测试

```powershell
# 全量测试
D:\Conda\envs\PBIAgent\python.exe -m pytest backend/tests -q

# Golden Cases
D:\Conda\envs\PBIAgent\python.exe -m backend.app.harness.cases

# 仓库安全检查（提交前必须执行）
D:\Conda\envs\PBIAgent\python.exe scripts/check_repository_safety.py

# 人工验收 Smoke（需 .env 中配置 DEEPSEEK_API_KEY，项目根目录执行）
D:\Conda\envs\PBIAgent\python.exe scripts\manual_smoke\deepseek_chat_smoke.py
```
### DeepSeek 配置

DeepSeek 配置由本地 `.env` 提供：
- `LLM_MODE=deepseek` — 启用 DeepSeek 模式
- `DEEPSEEK_API_KEY=<your_key_here>` — API Key（仅后端使用）
- `DEEPSEEK_BASE_URL=https://api.deepseek.com/v1` — API 地址
- `DEEPSEEK_MODEL=deepseek-chat` — 模型名称

代码 Agent 不读取 `.env`。Key 只在后端运行时使用。Smoke 输出经过脱敏。
`httpx` 属于运行依赖。

## 技术栈

| 层级 | 技术 | 状态 |
|------|------|------|
| 前端 | React + Vite | 骨架已确认，开发延后 (M5) |
| 后端 | FastAPI | ✅ M0.4 最小骨架已完成 |
| Agent | 确定性 TurnPipeline | ✅ M1.6.3 统一执行骨架 |
| LLM | DeepSeek + Mock LLM | ✅ Mock 可运行；DeepSeek Chat 全链路已封板 (M1.5) |
| 数据 | Power BI MCP | ✅ Local Desktop Demo 已完成 Business Golden 与 Bad Case 封板候选；Remote Deferred |
| 记忆 | 结构化工作记忆 | ✅ M0.2-M0.3.2 完整实现 |
| 报表 | 固定模板 HTML | ✅ Mock 可运行；真实渲染延后 (M3) |
| Harness | MVP 轻量控制面 | ✅ M2.6.1 独立 Oracle + 6 组多轮 MiniSuite 离线通过 |

## 文档导航

| 文档 | 说明 |
|------|------|
| `AGENTS.md` | Claude / Codex / 其他代码 Agent 的仓库级入口与架构边界 |
| `PROJECT_CHARTER.md` | 项目北极星，不可静默修改的核心约束 |
| `CLAUDE.md` | 通用代码 Agent 开发协议、Commit/Tag 规则、冷启动协议 |
| `docs/00_product_requirements_document.md` | 正式 PRD |
| `docs/08_development_roadmap.md` | 完整开发路线 |
| `docs/09_context_handoff.md` | 最新交接入口 |
| `docs/adr/` | 架构决策记录 |

## 许可证

专有软件，公司内部使用。

---

*最后更新：2026-08-12 | M2.6.1 Oracle 与多轮 Harness 离线固化完成；下一阶段 M2.6.2*
