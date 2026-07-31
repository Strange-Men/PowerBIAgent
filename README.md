# PowerBIAgent — Power BI 数据分析 Agent MVP

## 项目简介

PowerBIAgent 是供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。

核心链路：用户自然语言提问 → React 极简对话页面 → FastAPI 后端 → 单 Agent 意图识别 → DeepSeek → Power BI MCP → Power BI 语义模型 → 数据问答或固定模板静态 HTML 报表。

## 当前状态

**M1.0.1 幂等并发与文档收尾修复** — M0 开发准备阶段已完成。FastAPI 骨架、Health/Chat 接口已上线。Mock 模式完整闭环。

> **当前仅支持 Mock 模式。** 真实 DeepSeek 和 Power BI 尚未接入（计划 M1.1/M2）。

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

核心依赖：FastAPI、Uvicorn、pydantic-settings、pydantic-ai（版本已锁定，见 pyproject.toml）。httpx 为开发/测试依赖。

### 环境变量

项目使用 `.env` 文件和环境变量配置。Mock 模式启动不需要任何 API Key。

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
  "version": "M1.0",
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
```

## 技术栈

| 层级 | 技术 | 状态 |
|------|------|------|
| 前端 | React + Vite | 骨架已确认，开发延后 (M5) |
| 后端 | FastAPI | ✅ M0.4 最小骨架已完成 |
| Agent | PydanticAI 单 Agent | ✅ M0.2 已选定 |
| LLM | DeepSeek + Mock LLM | ✅ Mock 可运行；DeepSeek 延后 (M1.1) |
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

*最后更新：2026-07-31 | M1.0.1 幂等并发与文档收尾修复*
