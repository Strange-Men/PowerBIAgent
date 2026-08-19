# 09 — 当前上下文交接

> **当前状态入口。** 从根目录 `AGENTS.md` 开始；本文件只回答"现在是什么、下一步做什么"。历史变更见 `CHANGELOG.md` 与 Git。
> **最后更新：** 2026-08-19

## 当前阶段

**M4.1.2 — SQLite Transaction Failure & Error Semantics Hardening 已完成。** M4.1.1 基础上的强制硬化，不改变产品版本（Settings.version 仍为 M4.1.2）。

### 变更内容

#### Fix A — Locked transaction 内不继续查询

- 原 `commit()` 在捕获 `OperationalError("database is locked")` 后，在同一 session/transaction 中继续 `_get_latest_committed_version()` 查询。  SQLAlchemy transaction 在 OperationalError 后可能已进入 failed state，此时继续 query 不可靠。
- 修复：捕获 locked/busy 后立即退出原 transaction，委托 `_resolve_locked_commit_failure` helper 使用 **fresh session + fresh transaction** 重新读取 latest committed version。
- 新 helper 通过 `session_factory()` 创建全新 session，纯读取不修改业务状态，返回确定的 domain 异常。

#### Fix B — 真实 OperationalError 注入测试

- 当前 M4.1.1 测试只通过字符串分类验证 `_is_sqlite_locked` helper，不经过真实 `commit()` 路径。
- 新增 6 个测试，通过 `unittest.mock.patch.object(AsyncSession, 'execute')` 在 UPDATE 语句层级注入真实 `OperationalError`：

1. **non-lock OperationalError → PersistenceRepositoryError**：UPDATE 抛出 `OperationalError("disk I/O error")` → `_is_sqlite_locked` 返回 False → `PersistenceRepositoryError`
2. **locked + version advanced → MemoryVersionConflictError**：UPDATE 抛出 `"database is locked"`，fresh session reread 检测到 concurrent writer 已提交 target_version → `MemoryVersionConflictError`
3. **locked + unchanged → PersistenceRepositoryError**：UPDATE 抛出 `"database is locked"`，fresh session reread 发现版本未推进 → `PersistenceRepositoryError`
4. **fresh-session proof**：追踪 session 创建数量，证明 locked 后 reread 使用的是新 session（≥2 distinct sessions）
5. **failed tx recovery**：locked 失败后，后续 `get_by_request_id` 和 `create_pending` 使用 fresh session 正常工作
6. **no half-committed memory**：locked 失败后 memory 仍为 PENDING，memory_version 未推进，无 COMMITTED 行

#### Error Handling Structure

清晰保持边界：
- **IntegrityError**：仅 committed-version unique conflict → `MemoryVersionConflictError`；其他 IntegrityError 原样抛出
- **OperationalError A（locked/busy）**：退出原 transaction → fresh session bounded reread → `MemoryVersionConflictError`（version conflict）或 `PersistenceRepositoryError`（version not advanced）
- **OperationalError B（non-lock）**：disk I/O、corruption、unable to open DB → `PersistenceRepositoryError`

### 架构影响

- `backend/app/persistence/repositories/common.py` 新增 `_resolve_locked_commit_failure` helper
- `backend/app/persistence/repositories/memory.py` `commit()` 中 locked 分支简化为委托给 fresh-session helper
- Settings.version 保持 `M4.1`（frozen field，非功能版本号）
- 不新增 Alembic migration（schema 未变）
- 默认 `persistence_backend` 仍为 `memory`

## M4.2 下一步

后续轮次：

1. **M4.2**: Conversation/Report metadata recovery（重启后重建状态）
2. **M4.3**: 最近对话 API / 聊天搜索 API / 删除会话 API
3. **M4.4**: Restart/crash acceptance（E2E 验证重启后状态恢复）
4. **M5**: React + Vite 前端

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

*最后更新：2026-08-19 | M4.1.2 — SQLite Transaction Failure & Error Semantics Hardening*