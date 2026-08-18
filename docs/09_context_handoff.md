# 09 — 当前上下文交接

> **当前状态入口。** 从根目录 `AGENTS.md` 开始；本文件只回答"现在是什么、下一步做什么"。历史变更见 `CHANGELOG.md` 与 Git。
> **最后更新：** 2026-08-18

## 当前阶段

**M4.1 — SQLite 记忆与请求快照持久化已完成。** M4.0 持久化架构基础上新增 SQLiteMemoryRepository 与 SQLiteSnapshotRepository production wiring，以及 concurrent commit DB 级 invariant。

- **M4.0** 已建立本地持久化架构基础（SQLite + SQLAlchemy Async + aiosqlite + Alembic、5 表 schema、Repository ABC）。
- **M4.1** 已实现 SQLiteMemoryRepository 与 SQLiteSnapshotRepository，并通过 production wiring 注入到两个 TurnService。
- **M4.1 新增 DB 级并发提交 invariant**：`ix_work_memories_committed_version` partial unique index 保证同一 (runtime_mode, conversation_id, memory_version) 最多只有一个 COMMITTED 行。代码层 `IntegrityError`/`OperationalError` 均转换为 `MemoryVersionConflictError`。
- 当前 `persistence_backend` 默认仍为 `memory`，与 M4.0 保持相同。
- `persistence_backend=sqlite` 时通过 `SQLiteMemoryRepository` 与 `SQLiteSnapshotRepository` 提供跨重启持久化。
- Report metadata recovery、Conversation history/search 尚未完成（属于 M4.2+）。

### 记忆与持久化

- `MemoryRepository` 实现：`InMemoryMemoryRepository`（memory 后端）、`SQLiteMemoryRepository`（sqlite 后端）。
- `SnapshotRepository` 实现：`ResultSnapshotStore`（InMemory）、`SQLiteSnapshotRepository`（sqlite 后端）。
- `LocalReportRepository` 已将 HTML 文件写入 `local_state/reports/`，metadata 在进程内存中。
- 生产 wiring 根据 `persistence_backend` 自动选择：memory → InMemory repos；sqlite → SQLite repos。
- Alembic 迁移 head：`ab8d7df39a02`（新增 partial unique index）。

### 正式报表链（M3.4 不变）

```text
Natural Language
→ Intent / constrained language understanding
→ Template grounding（sales_report）
→ Bounded Report Intent weak signal
→ deterministic ReportPlanner
→ Canonical ReportPlan
→ N × CanonicalQueryPlan（M2 密封链）
→ N × Deterministic DAX → N × Independent Layer 3
→ N × ToolGateway → PowerBIAdapter → Power BI
→ N × QueryResult → N × VerifiedFactSet
→ deterministic SalesReportData
→ deterministic ReportSpec（KPI + charts）
→ SalesReportRenderer → static UTF-8 HTML
→ ReportArtifact → ReportRepository
→ report_id / view / download
→ Memory / Snapshot（SQLite 或 InMemory，取决于 persistence_backend）
```

### 测试矩阵

- 总测试数：**1559 passed**（较 M4.0 增加 42）。
- 新增严格 concurrent commit 测试：exactly-one-success + 8 轮多轮验证。
- Golden：`python -m backend.app.harness.cases` — 11 PASS / 1 SKIP（Real baseline）。
- 所有 Gates：architecture、safety、error ledger、documentation governance 全 PASS。

## M4.2 下一步

M4.1 已完成 SQLite Memory/Snapshot 持久化与并发安全。后续轮次：

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

*最后更新：2026-08-18 | M4.1 — SQLite 记忆与请求快照持久化*