# 09 — 跨对话上下文交接

> **所有新 Claude 恢复上下文的唯一最新交接入口。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-07-31 | M0.4 项目骨架与阶段收尾**

---

## 当前项目目标摘要

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言对话查询 Power BI 语义模型数据，并以固定模板生成静态 HTML 报表。

## 当前阶段

**M0.4 项目骨架与阶段收尾** — ✅ 已完成。M0 开发准备阶段全部完成。

## 已完成版本

| 版本 | 名称 | Commit SHA | 日期 |
|------|------|-----------|------|
| M0.1 | 仓库初始化与文档基线 | `eb5812d` | 2026-07-31 |
| M0.2 | 智能体架构与记忆设计 | `d03ac6c` | 2026-07-31 |
| M0.3 | 数据接入与验证闭环 | `c3510f2` | 2026-07-31 |
| M0.3.1 | 验证闭环加固修复 | `3c7cc7c` | 2026-07-31 |
| M0.3.2 | 工具网关与并发闭环修正 | `ec1afcc` | 2026-07-31 |
| M0.3.3 | Mock场景并发隔离修复 | `d0d47e3` | 2026-07-31 |
| M0.4 | 项目骨架与阶段收尾 | 由下一轮 git log -1 获取 | 2026-07-31 |

## 当前轮 Commit

**标题：** `M0.4_项目骨架与阶段收尾`

**Push 状态：** 待推送

## 最近封板 Tag

**`m0.4-foundation-release`** — M0 开发准备阶段封板 Tag。

## M0.4 交付内容

### 阶段A：请求级并发上下文收口

**已确认问题：** `MockTurnService._trace`、`ToolGateway._trace_recorder`、`ToolGateway._turn_controller` 为共享实例字段，同一 Service/Gateway 实例并发时后到达请求覆盖前一个请求的 Trace/Controller/工具计数。`_build_result()` 从共享 `self._trace` 读取，`_fail_turn()` 静默吞掉非法状态转换异常。

**修复：**
- **删除** `ToolGateway._trace_recorder`、`ToolGateway._turn_controller` 实例字段
- **删除** `ToolGateway.set_trace_recorder()`、`ToolGateway.set_turn_controller()` 方法
- **删除** `MockTurnService._trace` 实例字段
- `ToolGateway.execute()` 改为显式接收 `trace` 和 `controller` 可选参数：
  ```python
  async def execute(self, tool_name, execution_context, input_data, trace=None, controller=None)
  ```
- `MockTurnService._build_result()` 改为显式接收 `trace` 参数，工具序列来自 `trace.get_tool_sequence()`
- `MockTurnService._fail_turn()` 不再使用 `except Exception: pass` — 意外非法转换记录 Trace 后重新抛出 `RuntimeError`
- ToolGateway 保持为无请求状态，可安全并发复用

**新增并发测试（6 个）：**
- `TestSameServiceFullToolChainConcurrent`：同一 Service + Gateway + Runtime + Repository 并发 data_question vs report_generation，验证 trace_id/tool_sequence/Memory 互不污染 + 循环 10 次稳定性 + 工具计数独立
- `TestSameServiceFailAndSuccessConcurrent`：同一 Service 并发失败+成功，验证失败不污染成功请求的 Trace/Controller/Memory + 失败不阻塞成功 commit

### 阶段B：FastAPI 最小骨架

**新增文件：**
- `backend/app/config/settings.py` — Pydantic Settings（app_name/env/debug/host/port/log_level/llm_mode/powerbi_mode/harness_mode），环境变量可覆盖，Mock 无需 API Key，SecretStr 不泄露，`is_real_ready` 在 Real 模式未实现时返回 False
- `backend/app/config/__init__.py` — 导出 `Settings`、`get_settings()`
- `backend/app/api/schemas.py` — ChatRequest（extra="forbid"）、ChatResponse、HealthResponse、ErrorResponse
- `backend/app/api/dependencies.py` — 模块级共享 MockTurnService（lifespan 初始化）
- `backend/app/api/routes.py` — `GET /health`、`POST /api/v1/chat`
- `backend/app/api/__init__.py`
- `backend/app/main.py` — `create_app()` + lifespan + 共享 MockTurnService

**接口契约：**
- `GET /health` → `{"status":"ok","app_name":"PowerBIAgent","app_env":"development","version":"M0.4","llm_mode":"mock","powerbi_mode":"mock","harness_mode":"strict","timestamp":"..."}`
- `POST /api/v1/chat` → 非流式，message 非空，conversation_id/request_id 可自动生成，Real 模式返回 503，extra="forbid"

**新增依赖：** FastAPI 0.141.1

**API 测试（26 个）：**
- `test_settings.py`（18）：默认 Mock/环境变量覆盖/非法模式拒绝/Secret 不泄露/Real 未 ready/隔离/缓存
- `test_health.py`（8）：200/状态/字段/无敏感/不调用 LLM
- `test_chat.py`（13）：数据问答/报表/空消息 422/幂等/clarification/结构完整/Real 模式 503/额外字段 422/并发 data vs report + 不串场

### 阶段C：M0 全量验收

- compileall：通过
- 全量 pytest：**265 passed**（219 + 26 新增 + 20 Settings/Health/Chat）
- Golden Cases：**11/11 mock_ready 通过**，1 skipped (gc_012 pending_real_baseline)
- Uvicorn 启动验证：`/health` 返回 200，`/api/v1/chat` 数据问答和报表均成功
- Secret 检查：通过
- 无 .env 提交，无真实业务数据
- 原始 PRD 未修改

## 测试结果

**265/265 pytest 通过**（pytest 9.1.1，Python 3.11.15）

**Golden Cases：11/11 mock_ready 通过，1 skipped (pending_real_baseline)**

**compileall 通过**

**Uvicorn 启动验证通过**

## 目录结构（更新）

```
PowerBIAgent/
├── backend/
│   ├── app/
│   │   ├── main.py                        # M0.4 新增 — FastAPI 应用
│   │   ├── config/
│   │   │   ├── __init__.py                # M0.4 新增
│   │   │   └── settings.py               # M0.4 新增 — Pydantic Settings
│   │   ├── api/
│   │   │   ├── __init__.py               # M0.4 新增
│   │   │   ├── routes.py                 # M0.4 新增 — /health, /api/v1/chat
│   │   │   ├── schemas.py                # M0.4 新增 — 请求/响应模型
│   │   │   └── dependencies.py           # M0.4 新增 — 依赖注入
│   │   ├── application/mock_turn_service.py  # M0.4 修改 — 删除共享状态
│   │   ├── agent/mock_runtime.py
│   │   ├── harness/
│   │   │   ├── runtime/tool_gateway.py   # M0.4 修改 — 删除共享字段
│   │   │   └── ...
│   │   └── ...
│   └── tests/
│       ├── unit/test_settings.py         # M0.4 新增
│       ├── api/
│       │   ├── test_health.py            # M0.4 新增
│       │   └── test_chat.py              # M0.4 新增
│       └── integration/test_mock_pipeline.py  # M0.4 修改 — 新增 6 个并发测试
```

## 未验证事项

- 项目负责人 Power BI 账号状态（M2 前确认）
- DeepSeek API Key 可用性（M1 前确认）
- Entra App Registration 权限（M2 前确认）
- Power BI Tenant 设置（M2 前确认）
- Remote MCP Server 端点可用性（M2 早期验证）

## 下一阶段唯一允许范围

**下一阶段：** M1 真实 DeepSeek 接入

**允许：**
- DeepSeek Provider 真实实现（继承 LLMProvider）
- DeepSeek API Key 从 Settings 读取
- 意图识别真实 DeepSeek 调用
- QueryPlan/DAX/AnswerSpec/ReportSpec 真实 LLM 生成
- Mock 模式保持完整可用（Golden Cases 必须继续通过）
- 不可Mock场景应被Harness正确拒绝

**禁止：**
- 真实 Power BI MCP（M2）
- React 前端（M5）
- 流式 SSE
- 文件上传
- Docker
- 多 Agent / LangGraph
- 多租户 / RLS
- 修改原始 PRD
- 破坏 Golden Cases
- 新增未锁定依赖

## M0.4 必读文件（下一轮参考）

1. PROJECT_CHARTER.md
2. CLAUDE.md
3. docs/00_product_requirements_document.md
4. docs/09_context_handoff.md（本文件）
5. docs/08_development_roadmap.md
6. backend/app/config/settings.py
7. backend/app/main.py
8. backend/app/api/routes.py

---

*最后更新：2026-07-31 | M0.4 项目骨架与阶段收尾*
