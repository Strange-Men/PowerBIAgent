# 09 — 跨对话上下文交接

> **所有新 Claude 恢复上下文的唯一最新交接入口。**
> **每轮结束时覆盖更新，不追加失效信息。**
> **最后更新：2026-07-31 | M1.0.1 幂等并发与文档收尾修复**

---

## 当前项目目标摘要

开发供公司内部少量人员使用的 Power BI 数据分析 Agent MVP。用户通过自然语言对话查询 Power BI 语义模型数据，并以固定模板生成静态 HTML 报表。

## 当前阶段

**M1.0.1 幂等并发与文档收尾修复** — ✅ 已完成。

## 当前完成轮次

**M1.0.1** — 幂等并发与文档收尾修复

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
| M1.0 | M0遗留收口与M1路线固化 | `9247322` | 2026-07-31 |
| M1.0.1 | 幂等并发与文档收尾修复 | 最终 SHA 以 git log -1 为准 | 2026-07-31 |

## 当前轮 Commit

**标题：** `M1.0.1_幂等并发与文档收尾修复`

**Push 状态：** 将在 Git 收尾完成后推送

## 最近封板 Tag

| Tag | Commit | 说明 |
|-----|--------|------|
| `m0.4.1-foundation-release` | `1f967b0` | M0.4.1 封板 — 保留不动 |
| `m0.4-foundation-release` | `d5c1634` | M0.4 封板 — 保留不动 |

## M1.0 交付内容

### 修复1：clarification/unsupported 保留 conversation_id
### 修复2：request_id 幂等重放
### 修复3：默认报表模板 sales_weekly
### 修复4：版本号和安装说明
### M1.0—M1.5 路线固化

**Commit：** `9247322` M1.0_M0遗留收口与M1路线固化

## M1.0.1 交付内容

### 修复1：请求指纹与冲突检测
- 新增 `RequestFingerprint` 模型（`backend/app/memory/request_fingerprint.py`）
- message 首尾空白清理后参与指纹；client_conversation_id 使用客户端原始值
- 使用 Canonical JSON + SHA-256 生成稳定 Hash
- 相同 request_id、不同指纹 → `IdempotencyConflictError` → API 返回 HTTP 409
- 不将原始 message 或完整请求内容写入日志和 Trace

### 修复2：并发 Owner/Waiter 防重
- `IdempotencyTracker` 集成到 `ResultSnapshotStore`
- `claim()` / `complete()` / `abort()` 三个原子操作
- 使用 `asyncio.Lock` 保护 in-flight 字典，锁仅用于领取执行权
- 相同指纹并发请求：一个成为 Owner 执行，其余 Waiter 等待
- 不同指纹并发请求：立即冲突，不等待
- Owner 异常时清理 in-flight 并唤醒 Waiter，Waiter 可重试

### 修复3：Report 快照结构化
- 新增 `ReportResultSnapshot` Pydantic 模型（report_id/template_key/html 均为必填）
- `TurnResultSnapshot.report` 类型从 `Optional[dict]` 改为 `Optional[ReportResultSnapshot]`
- 保存快照时 Pydantic 校验，非法 report 不能进入快照 Store
- `TurnResultSnapshot` 增加跨字段校验（answer/report/clarification/unsupported 一致性）
- 快照包含 `request_fingerprint_hash` 字段

### 修复4：Service 统一 UUID 生成
- `MockTurnService.execute()` 签名：`conversation_id: str | None = None`、`request_id: str | None = None`
- 未传时 Service 统一生成 UUID（`str(uuid.uuid4())`）
- 指纹使用客户端原始 conversation_id（可能为 None）
- 重放返回首次请求保存的 effective conversation_id

### 修复5：文档状态收尾
- `docs/08`：M1.0 状态改为已完成，新增 M1.0.1 专项修复记录
- `docs/09`：当前轮次更新为 M1.0.1，下一轮仍为 M1.1
- 不再保留失效的进度标记。

## 测试结果

**pytest 基准：327 passed（M1.0）**

**Golden Cases：11/11 mock_ready 通过，1 skipped**

## 新增/修改文件

| 文件 | 变更 |
|------|------|
| `backend/app/memory/request_fingerprint.py` | **新增** — RequestFingerprint + IdempotencyConflictError |
| `backend/app/memory/result_snapshot.py` | 重写 — ReportResultSnapshot + IdempotencyTracker |
| `backend/app/application/mock_turn_service.py` | 重写 — 指纹/并发/UUID/结构化快照 |
| `backend/app/api/routes.py` | 新增 409 冲突处理 + 可选 ID 传递 |
| `README.md` | M1.0.1 功能说明 |
| `CHANGELOG.md` | M1.0.1 条目 |
| `docs/08_development_roadmap.md` | M1.0.1 专项修复记录 |
| `docs/09_context_handoff.md` | 本文件 — M1.0.1 完成状态 |
| `backend/tests/integration/test_m1_0_1_fixes.py` | **新增** — M1.0.1 专项测试 |
| `backend/tests/api/test_chat.py` | 新增 M1.0.1 API 测试 |

## 未完成或待观察事项

- 跨进程持久化和分布式锁延后处理
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

*最后更新：2026-07-31 | M1.0.1 幂等并发与文档收尾修复*
