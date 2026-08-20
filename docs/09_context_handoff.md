# 09 — 当前上下文交接

> **当前状态入口。** 从根目录 `AGENTS.md` 开始；本文件只回答"现在是什么、下一步做什么"。历史变更见 `CHANGELOG.md` 与 Git。
> **最后更新：** 2026-08-20

## 当前阶段

**M4.3 — 会话历史搜索与命名空间查询闭环已完成。**

M4.2 series 保持 FINAL PASS；M4.3 在其 persistence authority/invariant 基础上完成 SQLite recent/history/search/archive/delete，不改变 M0—M3 factual truth chain。

| 子版本 | 内容 | 状态 |
|--------|------|------|
| M4.2 series | 会话/报表恢复与 metadata authority 最终收口 | ✅ FINAL PASS |
| **M4.3** | **Conversation History / Search API** | **✅ 完成** |

### M4.3 authority 与 contract

- Conversation identity：`(runtime_mode, conversation_id)`；Repository 的 recent/history/search/archive/delete 均要求显式 `runtime_mode`。
- Report history identity：`(source_mode, conversation_id)`；report lookup/delete 的 namespace predicate 在 Repository 内固定，调用方不能漏 filter。
- `result_snapshots` 是 terminal turn history ledger；同 request committed `work_memories` 只补充 analysis/model/version；`report_artifacts` 继续走 M4.2.3 strict reconstruction。SQLite 不是 business/result/report factual authority。
- 当前 schema 不保存逐字 user/assistant message transcript；API 返回 structured history，不生成 transcript，不返回 report HTML、ORM row 或 `payload_json`。

### Recent / Search / Pagination

- Recent 只返回 unarchived root，固定排序 `updated_at DESC, conversation_id ASC`；terminal snapshot save 在同一 transaction touch exact namespace root，修复旧 `updated_at` 只在创建时可靠的问题。
- Search 只覆盖 committed `analysis_goal` 和 snapshot 的 `answer` / `clarification_question` / `unsupported_reason`；不搜索 HTML、DAX、任意 JSON 全文或未存储内容；未引入 FTS5。
- Page size 1—50；opaque keyset cursor 绑定 endpoint、namespace、search query 与 conversation/resource，非法 limit/cursor 显式 422；unknown conversation 一致 404。

### Archive / Delete

- Archive：幂等逻辑隐藏，设置 `archived_at`；从 recent/search 排除，但 direct history/reports 仍可读。
- Delete：同一 DB transaction 物理删除该 namespace 的 work memory、snapshot、pending clarification、同 source_mode report metadata 与 conversation root；随后 `LocalReportRepository` 删除精确 report_id HTML。相同 conversation_id 的另一 namespace 不受影响。
- Filesystem HTML 仍是报表内容 authority；DB 只保存 metadata。

### 架构影响

- `backend/app/conversation/`：DTO + namespace-first repository ABC。
- `backend/app/application/conversation_history_service.py`：limit/query/cursor validation 与 delete filesystem orchestration。
- `backend/app/persistence/repositories/conversation_history.py`：SQLite queries/mutations；API/router 不写 SQLAlchemy。
- Migration `f4c3a2b1907d`：`conversations.archived_at` 与 namespace recent/history/report indexes；fresh DB 和 M4.2.3 revision upgrade 均通过。
- `backend/app/config/settings.py`：version → M4.3。
- 新增 20 个 SQLite/API tests；全仓 `1673 passed, 1 skipped`；persistence `193 passed, 1 skipped`。
- 不新增 tag。

## 下一步

后续轮次：

1. **M4.4**: Restart/crash acceptance（NOT STARTED；本轮未实现 crash-process E2E）
2. **M5**: React + Vite 前端（NOT STARTED）

## 关键命令

```powershell
# Full test suite
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests -q --asyncio-mode=auto

# Persistence-focused
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests\unit\persistence -v --asyncio-mode=auto

# Golden
D:\Conda\envs\PBIAgent\python.exe -m backend.app.harness.cases

# Alembic smoke（从空 DB）
D:\Conda\envs\PBIAgent\python.exe -m alembic upgrade head

# Gates
D:\Conda\envs\PBIAgent\python.exe scripts\check_architecture_gate.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_repository_safety.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_ai_error_ledger.py
D:\Conda\envs\PBIAgent\python.exe scripts\check_documentation_governance.py
```

---

*最后更新：2026-08-20 | M4.3 — 会话历史搜索与命名空间查询闭环*
