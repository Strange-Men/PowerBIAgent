# 09 — 当前上下文交接

> **当前状态入口。** 从根目录 `AGENTS.md` 开始；本文件只回答"现在是什么、下一步做什么"。历史变更见 `CHANGELOG.md` 与 Git。
> **最后更新：** 2026-08-19

## 当前阶段

**M4.1.3 — SQLite Lock Transaction Exit Final Hardening 已完成。**

### 变更内容

#### Fix A — locked failure 必须退出原 transaction 再 fresh-session resolution

M4.1.2 的 `_resolve_locked_commit_failure` 虽创建新 session，但在 `async with session.begin()` 异常处理器内部被调用，此时原 SQLAlchemy session.begin() context 尚未退出，原 transaction 可能仍处于 failed/poisoned 状态。

M4.1.3 重构 `commit()` 的 locked 分支：

1. **在 transaction 内**：捕获 locked OperationalError 后只保存 failure context（conversation_id、runtime_mode、target_version），不调用 resolver。
2. **让 `session.begin()` context 自然退出**：`session.begin()` 的 `__aexit__` 触发 rollback，原 transaction 完全终止。
3. **transaction context 退出后**：`_locked_failure_ctx` 非空则调用 `_resolve_locked_commit_failure` 使用 **全新 session + 全新 transaction** 重新读取 latest committed version。
4. resolver 始终抛出确定的 domain 异常：`MemoryVersionConflictError`（version advanced）或 `PersistenceRepositoryError`（version not advanced）。

成功路径完全不变：全部在单一 transaction 内。

#### Fix B — 真实 SQLite lock integration test

新增 3 个测试（`TestTransactionExitBeforeReread`）：

1. **`test_real_sqlite_lock_triggers_locked_path`**：两个独立 engine，Writer A 持有真实 SQLite write lock，Writer B 的 commit() 触发真实 SQLITE_BUSY → 走 locked path → PersistenceRepositoryError。释放锁后验证 memory 仍为 PENDING、无 half-commit。
2. **`test_real_sqlite_lock_precreated_pending`**：预创建 conversation 和 pending（避免 ensure_conversation 被锁阻塞），Writer A 持有锁，B 的 UPDATE 被锁 → locked path → PersistenceRepositoryError。验证顺序正确。
3. **`test_session_exit_sequence_proof`**：instrumented session factory + event markers 断言 locked 路径被命中、至少 2 个 distinct session（commit session + fresh reread session）、locked 后 memory 仍为 PENDING。

不依赖 sleep-based 同步，使用明确的 connection/tx 生命周期控制。

#### Error Handling Structure（M4.1.3 最终版）

清晰保持边界：
- **IntegrityError**：仅 committed-version unique conflict → `MemoryVersionConflictError`；其他 IntegrityError 原样抛出
- **OperationalError A（locked/busy）**：transaction 内只保存上下文 → transaction 完全退出/rollback → **transaction 外** fresh session bounded reread → `MemoryVersionConflictError`（version conflict）或 `PersistenceRepositoryError`（version not advanced）
- **OperationalError B（non-lock）**：disk I/O、corruption、unable to open DB → `PersistenceRepositoryError`

### 架构影响

- `backend/app/persistence/repositories/memory.py` `commit()` 中 locked 分支改为：捕获时只保存 context，resolver 调用移至 transaction context 退出后
- `backend/app/persistence/repositories/common.py` `_resolve_locked_commit_failure` docstring 更新（M4.1.3 语义强化）
- `backend/app/persistence/__init__.py` `create_engine` 新增可选的 `busy_timeout` 参数（测试缩短至 100ms，production 默认 5000ms）
- Settings.version 更新为 `M4.1.3`
- 不新增 Alembic migration（schema 未变）
- 默认 `persistence_backend` 仍为 `memory`

### M4.1 series FINAL PASS

M4.1 系列（M4.1 → M4.1.1 → M4.1.2 → M4.1.3）全部完成：

**M4.1**
- SQLite Memory/Snapshot persistence
- production wiring
- restart repository proof

**M4.1.1**
- conversation root race hardening
- narrowed error semantics

**M4.1.2**
- fresh-session resolver
- real OperationalError injection

**M4.1.3**
- transaction-exit-before-reread
- real SQLite lock integration

**M4.2：NOT STARTED**

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

*最后更新：2026-08-19 | M4.1.3 — SQLite Lock Transaction Exit Final Hardening*