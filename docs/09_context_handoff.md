# 09 — 跨对话上下文交接

> **所有新 Claude 恢复上下文的唯一最新交接入口。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-07-31 | M0.4.1 API骨架真实性修复**

---

## 当前项目目标摘要

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言对话查询 Power BI 语义模型数据，并以固定模板生成静态 HTML 报表。

## 当前阶段

**M0.4.1 API骨架真实性修复** — ✅ 已完成。M0 开发准备阶段彻底完成。

## 已完成版本

| 版本 | 名称 | Commit SHA | 日期 |
|------|------|-----------|------|
| M0.1 | 仓库初始化与文档基线 | `eb5812d` | 2026-07-31 |
| M0.2 | 智能体架构与记忆设计 | `d03ac6c` | 2026-07-31 |
| M0.3 | 数据接入与验证闭环 | `c3510f2` | 2026-07-31 |
| M0.3.1 | 验证闭环加固修复 | `3c7cc7c` | 2026-07-31 |
| M0.3.2 | 工具网关与并发闭环修正 | `ec1afcc` | 2026-07-31 |
| M0.3.3 | Mock场景并发隔离修复 | `d0d47e3` | 2026-07-31 |
| M0.4 | 项目骨架与阶段收尾 | `d5c1634` | 2026-07-31 |
| M0.4.1 | API骨架真实性修复 | 由下一轮 git log -1 获取 | 2026-07-31 |

## 当前轮 Commit

**标题：** `M0.4.1_API骨架真实性修复`

**Push 状态：** 待推送

## 最近封板 Tag

| Tag | Commit | 说明 |
|-----|--------|------|
| `m0.4.1-foundation-release` | 本轮 Commit | M0.4.1 封板 |
| `m0.4-foundation-release` | `d5c1634` | M0.4 封板 — 保留不动 |

## M0.4.1 交付内容

### 修复1：依赖可复现

- `pyproject.toml`：fastapi==0.141.1、uvicorn[standard]==0.52.0、pydantic-settings==2.14.2 写入运行时依赖；httpx==0.28.1 写入测试依赖
- `environment.yml`：启用 `-e .`；`pip install -e .` + `pip check` 验证通过

### 修复2：公开API真实意图流

- 新增 `backend/app/application/mock_scenario_resolver.py` — MockScenarioResolver
- API 路由不再构造 `MockScenarioSelection`；Mock 场景由 Application 层内部确定
- 支持 data_question / report_generation / clarification / unsupported 四类意图自动推断
- Golden Cases 仍可通过显式传 scenario 跳过 Resolver

### 修复3：返回真实Answer和Report

- `MockTurnService._build_result()` 保存实际 `AnswerSpec.answer` 和 `RenderedReport` 数据
- `ChatResponse` 新增结构化 `ReportResponse`（report_id/template_key/html）
- clarification 返回 clarification_question；unsupported 返回 unsupported_reason

### 修复4：Health真实性

- `HealthResponse` 新增 `ready`（bool）和 `reasons`（list[str]）
- Mock 模式：200/ready=true；DeepSeek 模式：503/ready=false；Remote MCP 模式：503/ready=false
- 使用 `response.status_code` 正确设置 HTTP 状态码

### 修复5：app.state与真实lifespan

- 删除模块级全局 `_mock_turn_service` 和 `set_mock_turn_service()`
- `app.state.settings` 和 `app.state.mock_turn_service` 在 lifespan 中初始化
- 依赖函数从 `request.app.state` 读取（不再使用全局变量或全局缓存）
- `create_app(settings=...)` 支持测试注入
- 测试使用 `app.router.lifespan_context(app)` + `ASGITransport` 真实触发 lifespan

## 测试结果

**285/285 pytest 通过**（pytest 9.1.1，Python 3.11.15）

**Golden Cases：11/11 mock_ready 通过，1 skipped (pending_real_baseline)**

**compileall 通过 | pip check 通过**

**Uvicorn 启动验证：**
- Mock Health：200、ready=true ✅
- 数据问答 answer：真实 AnswerSpec.answer ✅
- 报表 report：report_id + template_key + HTML ✅
- unsupported：unsupported_reason 真实返回 ✅

## 新增/修改文件

| 文件 | 变更 |
|------|------|
| `pyproject.toml` | 新增 fastapi/uvicorn/pydantic-settings 运行时依赖；httpx 测试依赖 |
| `environment.yml` | 启用 `-e .` |
| `README.md` | 版本锁定标注 |
| `backend/app/main.py` | 使用 app.state；create_app(settings=...) |
| `backend/app/api/routes.py` | 移除 Scenario 构造；Health 503；Response 状态码 |
| `backend/app/api/schemas.py` | ReportResponse；HealthResponse.ready/reasons |
| `backend/app/api/dependencies.py` | 删除全局变量；使用 request.app.state |
| `backend/app/application/mock_turn_service.py` | MockScenarioResolver 集成；真实 Answer/Report 保存 |
| `backend/app/application/mock_scenario_resolver.py` | **新增** — 内部场景解析器 |
| `backend/tests/api/test_health.py` | 重写 — lifespan 集成、503 验证、ready/reasons |
| `backend/tests/api/test_chat.py` | 重写 — 真实 answer/report/clarification/unsupported |

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
- 删除或移动 `m0.4-foundation-release` Tag

## M0.4.1 必读文件（下一轮参考）

1. PROJECT_CHARTER.md
2. CLAUDE.md
3. docs/00_product_requirements_document.md
4. docs/09_context_handoff.md（本文件）
5. docs/08_development_roadmap.md
6. backend/app/config/settings.py
7. backend/app/main.py
8. backend/app/api/routes.py
9. backend/app/api/schemas.py
10. backend/app/api/dependencies.py
11. backend/app/application/mock_turn_service.py
12. backend/app/application/mock_scenario_resolver.py

---

*最后更新：2026-07-31 | M0.4.1 API骨架真实性修复*
