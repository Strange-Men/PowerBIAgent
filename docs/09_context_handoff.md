# 09 — 跨对话上下文交接

> **所有新 Claude 恢复上下文的唯一最新交接入口。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-07-31 | M1.0 M0遗留收口与M1路线固化**

---

## 当前项目目标摘要

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言对话查询 Power BI 语义模型数据，并以固定模板生成静态 HTML 报表。

## 当前阶段

**M1.0 M0遗留收口与M1路线固化** — 🔄 进行中。

## 当前完成轮次

**M1.0** — M0遗留收口与M1路线固化

## 下一轮

**M1.1 DeepSeek Provider基础接入**

M1.2—M1.5：未开始

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
| M0.4.1 | API骨架真实性修复 | `1f967b0` | 2026-07-31 |
| M1.0 | M0遗留收口与M1路线固化 | 由下一轮 git log -1 获取 | 2026-07-31 |

## 当前轮 Commit

**标题：** `M1.0_M0遗留收口与M1路线固化`

**Push 状态：** 待推送

## 最近封板 Tag

| Tag | Commit | 说明 |
|-----|--------|------|
| `m0.4.1-foundation-release` | `1f967b0` | M0.4.1 封板 — 保留不动 |
| `m0.4-foundation-release` | `d5c1634` | M0.4 封板 — 保留不动 |

## M1.0 交付内容

### 修复1：clarification/unsupported 保留 conversation_id

- `_build_result()` 新增显式 `conversation_id` 参数
- clarification/unsupported 路径传入当前 `conversation_id`，不再依赖 Memory
- `conversation_id` 非空断言：memory 存在时取 memory 值，否则取参数值
- 空字符串不覆盖有效 conversation_id
- Service 直接调用和 FastAPI 调用均成立

### 修复2：request_id 幂等重放

- 新增 `TurnResultSnapshot` Pydantic 模型（`backend/app/memory/result_snapshot.py`）
- 新增 `ResultSnapshotStore` — 按 (runtime_mode, request_id) 复合键存储
- 首次请求保存快照（含 Answer/Report/clarification/unsupported/失败），重复请求返回完整快照
- 重放：terminal_state="duplicate"、tool_sequence=[]、memory_commit=false、新 trace_id
- `ChatResponse` 新增 `idempotent_replay: bool` 和 `replayed_request_id: Optional[str]`
- 快照检查先于 Memory 检查，覆盖 clarification/unsupported（无 Memory）的幂等

### 修复3：默认报表模板 sales_weekly

- `MockScenarioResolver.resolve()` 返回 `MockScenarioResolution`（含 `effective_report_template_key`）
- 客户端未传模板但消息含报表关键词 → effective_report_template_key = "sales_weekly"
- 客户端显式传模板 → 优先使用客户端模板
- `report_template_key` 贯穿：Context → Memory → ReportSpec → RenderedReport → API 响应
- `memory.report_template_key` 在成功报表请求中不为 None
- 普通数据问答不写入 `report_template_key`

### 修复4：版本号和安装说明

- Settings.version 更新为 `M1.0`
- Health 返回 `version: "M1.0"`
- README 新增 `pip install -e ".[dev]"` 开发依赖安装说明
- README Health 示例增加 `ready`/`reasons` 字段
- README Chat 示例与真实响应契约一致
- httpx 标注为开发/测试依赖

### M1.0—M1.5 路线固化

- `docs/08_development_roadmap.md` 写入完整 M1.0—M1.5 六轮路线
- 路线执行规则：顺序执行、未验收不进入下一轮、不允许跨轮
- `docs/08` 是小轮路线唯一权威来源
- `CLAUDE.md` 不重复粘贴完整路线

## 测试结果

**327/327 pytest 通过**（pytest 9.1.1，Python 3.11.15）

**Golden Cases：11/11 mock_ready 通过，1 skipped (pending_real_baseline)**

**compileall 通过 | pip check 通过**

新增测试：
- `backend/tests/integration/test_m1_fixes.py` — 30 个测试（conversation_id 5 + 幂等重放 10 + 报表模板 5 + 版本/文档验证 5 + 其他）
- `backend/tests/api/test_chat.py` 新增 M1.0 API 测试类（幂等重放、conversation_id、报表模板、版本验证、并发）

## 新增/修改文件

| 文件 | 变更 |
|------|------|
| `backend/app/memory/result_snapshot.py` | **新增** — TurnResultSnapshot + ResultSnapshotStore |
| `backend/app/application/mock_turn_service.py` | 重写 — conversation_id 参数、快照保存、幂等重放 |
| `backend/app/application/mock_scenario_resolver.py` | 重写 — MockScenarioResolution + effective_report_template_key |
| `backend/app/api/schemas.py` | 新增 idempotent_replay/replayed_request_id 字段 |
| `backend/app/api/routes.py` | 透传幂等重放字段 |
| `backend/app/config/settings.py` | version → M1.0 |
| `README.md` | M1.0 状态、dev install、Health/Chat 示例更新 |
| `CHANGELOG.md` | M1.0 条目 |
| `docs/08_development_roadmap.md` | M1.0—M1.5 完整路线 |
| `docs/09_context_handoff.md` | 本文件 — M1.0 完成状态 |
| `backend/tests/integration/test_m1_fixes.py` | **新增** — 30 个 M1.0 专项测试 |
| `backend/tests/api/test_chat.py` | 新增 M1.0 API 测试类 |
| `backend/tests/api/test_health.py` | version 期望更新为 M1.0 |
| `backend/tests/unit/test_settings.py` | test_version_is_m1_0 |

## 未完成或待观察事项

- 项目负责人 Power BI 账号状态（M2 前确认）
- DeepSeek API Key 可用性（M1.1 前确认）
- Entra App Registration 权限（M2 前确认）
- Power BI Tenant 设置（M2 前确认）
- Remote MCP Server 端点可用性（M2 早期验证）

## M1.1 允许范围

**下一轮：** M1.1 DeepSeek Provider基础接入

**允许：**
- 从 Settings 读取 API Key、Base URL、模型名
- 实现 DeepSeekLLMProvider
- 超时、鉴权、限流、网络和服务错误分类
- 最小真实连通测试
- Mock 模式保持完整可用

**M1.1 禁止提前实现：**
- 真实 Intent 业务流程
- 真实 QueryPlan / DAX / Answer / ReportSpec 生成
- 真实 Power BI 连接
- React 前端 / SSE / Docker / Redis / LangGraph / 多 Agent
- 修改历史 Tag

---

*最后更新：2026-07-31 | M1.0 M0遗留收口与M1路线固化*
