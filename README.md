# PowerBIAgent — Power BI 数据分析 Agent MVP

## 项目简介

PowerBIAgent 是供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。

核心链路：用户自然语言提问 → React 极简对话页面 → FastAPI 后端 → 确定性 TurnPipeline 编排（意图识别 → QueryPlan → DAX → Answer → ReportSpec）→ DeepSeek（受控结构化 LLM 调用）→ Power BI MCP → Power BI 语义模型 → 数据问答或固定模板静态 HTML 报表。

## 当前状态

**M1.7.2 M0—M1 最终封板基线** — M0—M1 正式封板前最后一个版本，只修正文档状态并建立封板流程。M2 尚未开始。

> **Mock + Mock 模式完整可用。** **DeepSeek + Mock 模式 Chat 已可用（需配置 API Key）。** QueryResult 仍为 Mock。真实 Power BI 尚未接入（M2）。当前版本 M1.7.2 M0—M1 最终封板基线。

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

核心依赖：FastAPI、Uvicorn、pydantic-settings、httpx（版本已锁定，见 pyproject.toml）。

### 环境变量

项目使用 `.env` 文件和环境变量配置。Mock 模式启动不需要任何 API Key。

#### 创建本地 .env

```powershell
Copy-Item .env.example .env
```

然后：
- `.env` 由用户本人本地填写真实 API Key
- `.env` 禁止提交（已在 `.gitignore` 中排除）
- Claude 和其他自动化工具不得读取 `.env` 内容
- DeepSeek API Key 只在后端运行时使用
- 前端永远不保存模型 API Key

#### 环境变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_ENV` | `development` | 运行环境 (development/test/production) |
| `LLM_MODE` | `mock` | LLM 模式 (mock/deepseek) |
| `POWERBI_MODE` | `mock` | Power BI 模式 (mock/remote_mcp) |
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
  "reasons": [],
  "app_name": "PowerBIAgent",
  "app_env": "development",
  "version": "M1.7.2",
  "llm_mode": "mock",
  "powerbi_mode": "mock",
  "harness_mode": "strict",
  "timestamp": "2026-07-31T07:03:23Z"
}
```

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

Claude 不读取 `.env`。Key 只在后端运行时使用。Smoke 输出经过脱敏。
`httpx` 属于运行依赖。

## 技术栈

| 层级 | 技术 | 状态 |
|------|------|------|
| 前端 | React + Vite | 骨架已确认，开发延后 (M5) |
| 后端 | FastAPI | ✅ M0.4 最小骨架已完成 |
| Agent | 确定性 TurnPipeline | ✅ M1.6.3 统一执行骨架 |
| LLM | DeepSeek + Mock LLM | ✅ Mock 可运行；DeepSeek Chat 全链路已封板 (M1.5) |
| 数据 | Power BI MCP | ✅ Mock 可运行；真实接入延后 (M2) |
| 记忆 | 结构化工作记忆 | ✅ M0.2-M0.3.2 完整实现 |
| 报表 | 固定模板 HTML | ✅ Mock 可运行；真实渲染延后 (M3) |
| Harness | MVP 轻量控制面 | ✅ M0.3-M0.4 ETCLOVG 完整实现 |

## 文档导航

| 文档 | 说明 |
|------|------|
| `PROJECT_CHARTER.md` | 项目北极星，不可静默修改的核心约束 |
| `CLAUDE.md` | 开发协议、Commit/Tag 规则、冷启动协议 |
| `docs/00_product_requirements_document.md` | 正式 PRD |
| `docs/08_development_roadmap.md` | 完整开发路线 |
| `docs/09_context_handoff.md` | 最新交接入口 |
| `docs/adr/` | 架构决策记录 |

## 许可证

专有软件，公司内部使用。

---

*最后更新：2026-08-05 | M1.7.2 M0—M1 最终封板基线*
