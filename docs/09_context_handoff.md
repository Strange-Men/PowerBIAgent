# 09 — 当前上下文交接

> **当前状态入口。** 从根目录 `AGENTS.md` 开始；本文件只回答"现在是什么、下一步做什么"。历史变更见 `CHANGELOG.md` 与 Git。
> **最后更新：** 2026-08-19

## 当前阶段

**M4.2 — 会话与报表元数据恢复 已完成。**

### M4.1 series FINAL PASS

M4.1 系列（M4.1 → M4.1.1 → M4.1.2 → M4.1.3）全部完成。

### M4.2 变更内容

#### A — Report metadata persistent repository

新增 `ReportArtifactRepository` 抽象接口，包含 `save()`、`get()`、`exists()` 方法。`SQLiteReportArtifactRepository` 使用现有 `report_artifacts` 表（无需 migration）持久化 report metadata；`InMemoryReportArtifactRepository` 用于 memory backend 兼容。

主要边界：
- HTML 正文始终存储在 `local_state/reports/<report_id>.html`（filesystem），数据库不存储 HTML blob
- `relative_path` 列指向 filesystem 路径，非 HTML 内容
- 注释禁止 path traversal（路径由 report_id 固定构建）
- UUIDv4 PK 碰撞由 DB 约束保证

#### B — LocalReportRepository 持久化集成

- `LocalReportRepository` 新增可选的 `metadata_repo` 参数
- `store()`：原子 filesystem 写入 → metadata repository 保存；metadata 失败时清理已写入的 HTML 文件
- `get()` / `read_html()` 优先查询进程内 `_items` cache，miss 时通过 metadata repository 恢复（重启 recovery 路径）
- `read_html()` 增加 `_validate_path()`：根据 report_id 安全构建目标路径，验证文件存在和 content_hash
- 篡改后的 HTML 文件 → `ReportStorageError`（report_content_hash_mismatch）
- 缺失 HTML 文件 → `ReportNotFoundError`

#### C — Memory/Snapshot 重启恢复

M4.1 已实现的 Memory/Snapshot restart recovery 路径保持不变，补充验证：
- committed Memory 重启后续读 continuation
- PendingClarification 重启后恢复
- Snapshot 重启后重放
- failed Memory 不进入恢复上下文
- Mock/Real namespace 重启后隔离

#### D — Wiring

- `main.py` `_create_repos()` 扩展为 5 元组返回，包含 `ReportArtifactRepository`
- SQLite backend：`SQLiteReportArtifactRepository` 复用同一 engine/session_factory
- Memory backend：`InMemoryReportArtifactRepository`
- `report_repository` 的创建移至 `_create_repos` 调用之后，接收 `metadata_repo=report_artifact_repo`
- Settings.version → `M4.2`

### 架构影响

- `backend/app/persistence/repositories/report_artifact.py`（新文件）：`ReportArtifactRepository` 抽象 + `SQLiteReportArtifactRepository` + `InMemoryReportArtifactRepository`
- `backend/app/report/resources.py` `LocalReportRepository` 改造：metadata_repo 注入、_resolve_artifact 重启恢复、_validate_path 安全路径
- `backend/app/main.py`：`_create_repos` 返回 5 元组，wiring 顺序调整
- `backend/app/config/settings.py`：version → M4.2
- 不新增 Alembic migration（report_artifacts 表现有 schema 足够）
- 默认 `persistence_backend` 仍为 `memory`
- 不新增 tag

### M4.2 PASS

## M4.3 下一步

后续轮次：

1. **M4.3**: 最近对话 API / 聊天搜索 API / 删除会话 API（NOT STARTED）
2. **M4.4**: Restart/crash acceptance（E2E 验证重启后状态恢复）
3. **M5**: React + Vite 前端

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