# 09 — 当前上下文交接

> **当前状态入口。** 从根目录 `AGENTS.md` 开始；本文件只回答"现在是什么、下一步做什么"。历史变更见 `CHANGELOG.md` 与 Git。
> **最后更新：** 2026-08-18

## 当前阶段

**M4.1.1 — 会话创建竞态与数据库错误语义加固已完成。** M4.1 基础上的 hardening，不改变产品版本（Settings.version 仍为 M4.1）。

### 变更内容

#### Fix A — Transaction-safe conversation root upsert

- 抽取共享 `ensure_conversation` helper 至 `repositories/common.py`
- 使用 SQLite 原生 `INSERT OR IGNORE` 代替原 `SELECT → INSERT → catch IntegrityError → expunge` 模式
- 新方案不会污染 transaction state，并发首次插入同一 (runtime_mode, conversation_id) 时原子性 no-op
- MemoryRepository 和 SnapshotRepository 均委托该共享 helper

#### Fix B — 缩窄数据库错误语义映射

- `commit()` 中 `IntegrityError` 仅当错误消息包含 committed-version partial unique index 的三列（runtime_mode, conversation_id, memory_version）时才转 `MemoryVersionConflictError`；其他 IntegrityError（FK、NOT NULL）re-raise
- `OperationalError` 区分 SQLite busy/locked 条件 vs 磁盘 I/O、损坏等非锁错误；非锁错误转为 `PersistenceRepositoryError`；锁冲突时 bounded re-read 最新版本，版本过时转 `MemoryVersionConflictError`，未过时转 `PersistenceRepositoryError`
- 新增 `PersistenceRepositoryError` 异常类（`repositories/common.py`），最小异常体系，不建立复杂层次

#### 新增测试（9 个）

- **4 个 conversation first-create race tests**：两个独立 session 同时首次创建同 conversation（不同 request_id 均成功、conversations 表 1 行）；Memory + Snapshot 同时首次创建同 conversation root；8 轮多轮验证；serial idempotent 验证
- **5 个 error semantics tests**：committed-version unique conflict → `MemoryVersionConflictError`；unrelated IntegrityError 不吞噬；`_is_sqlite_locked` 正确识别锁/非锁消息；`_is_version_index_conflict` 正确识别三列组合；failed transaction 后后续操作正常

### 架构影响

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

*最后更新：2026-08-18 | M4.1.1 — 会话创建竞态与数据库错误语义加固*