# 09 — 当前上下文交接

> **当前状态入口。** 从根目录 `AGENTS.md` 开始；本文件只回答"现在是什么、下一步做什么"。历史变更见 `CHANGELOG.md` 与 Git。
> **最后更新：** 2026-08-18

## 当前阶段

**M4.0 — Local Persistence Architecture & Storage Foundation 已完成。**

M0—M3 Final Seal：`m3.4-m0-m3-final-seal` → `ff8aca239c8b71709e351382eb381cc1337392c6`。

M4.0 在 main 完成，建立本地持久化架构基础：

- **SQLite + SQLAlchemy Async + aiosqlite + Alembic** 技术栈固定，依赖已安装并锁定版本（SQLAlchemy 2.0.52、aiosqlite 0.22.1、alembic 1.19.1）。
- **`backend/app/persistence/` 包**：database.py（AsyncEngine/sessionmaker/PRAGMA 生命周期）、models.py（5 表 ORM 持久化模型）、serialization.py（Pydantic ↔ JSON 序列化）。
- **数据库 schema**（5 表）：conversations（复合 PK `runtime_mode + conversation_id`）、work_memories（复合 FK）、pending_clarifications（复合 FK）、result_snapshots（复合 FK）、report_artifacts。关键约束：复合 PK 实现 Mock/Real 命名空间隔离；复合 FK 确保子表记录无法跨命名空间错误关联。
- **Alembic 迁移**：初始迁移 `42821213393c` + corrective migration `01dc0d90d920`（复合 PK/FK 加固）。
- **Settings 扩展**：新增 `PersistenceBackend`（memory | sqlite）、`persistence_database_path`（默认 `local_state/persistence/powerbiagent.db`）。默认 `memory`，不强制创建 SQLite。
- **Repository 抽象清理**：`TurnPipeline` 构造函数从 `InMemoryMemoryRepository` 改为 `MemoryRepository`；新增 `SnapshotRepository` ABC；`SnapshotRepository` → `ResultSnapshotStore` 继承。Services 构造函数的类型提示相应更新。
- **JSON 序列化策略**：`domain_to_json()` 使用 `model_dump(mode="json")`；`json_to_domain()` 使用 `model_validate()`；禁止 pickle/secret/raw LLM response。
- **PRAGMA 生命周期修复**：`foreign_keys = ON` 和 `busy_timeout = 5000` 通过 SQLAlchemy 连接池事件（`event.listen`）在每个新 DBAPI 连接上设置，不再只配置第一个连接。`journal_mode = WAL` 保持数据库级别，仅初始化一次。
- **测试**：40 个持久化测试（26 原始 + 14 corrective），全仓 1517 全 PASS。

## M4.0 核心架构决定

- 数据库是 **persistence provider**，不是新的 business authority。
- TurnPipeline / Memory commit rules 仍然是业务 authority。
- TurnPipeline 不得直接访问 SQLAlchemy Session（通过 Repository ABC 隔离）。
- HTML 文件继续存储在 `local_state/reports/`，数据库只保存 metadata。
- `journal_mode = WAL` 通过 `configure_engine()` 在数据库级别设置一次（持久化）。
- `foreign_keys = ON` 和 `busy_timeout = 5000` 通过 SQLAlchemy 连接池事件在每个新连接上设置。

## 当前状态

### 记忆与持久化

- `MemoryRepository` 接口已定义（pending/committed/failed/optimistic version...），当前实现为 `InMemoryMemoryRepository`。
- `SnapshotRepository` 接口已定义，当前实现为 `ResultSnapshotStore`（InMemory）。
- `LocalReportRepository` 已将 HTML 文件写入 `local_state/reports/`，metadata 在进程内存中。
- 生产 Memory / Snapshot / Report metadata 尚未切换 SQLite（属于 M4.1+）。

### 正式报表链（不变）

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
→ Memory / Snapshot（当前 InMemory）
```

### TurnPipeline 唯一控制面（不变）

- ID 生成、请求指纹、Owner/Waiter 幂等协调、TraceRecorder、TurnController、ContextBuilder、Memory 失败标记、Snapshot 保存/重放/abort。
- Mock 和 DeepSeek 路径共享同一执行骨架（TurnPipeline）。
- Service 不持有 memory_repo 或 snapshot_store 实例字段。

### 测试矩阵

- 总测试数：1517 passed（1477 基线 + 40 持久化测试）。
- 持久化测试覆盖：engine lifecycle、migration upgrade head、DB 文件创建/gitignore、ABC 抽象、serialization roundtrip/corruption、UNIQUE/FK/PRAGMA、settings、复合 PK/FK 约束验证、conversation 命名空间隔离、每连接 PRAGMA。
- Golden：`python -m backend.app.harness.cases`（M3.4 验证，11 PASS）。

## M4.1 下一步

M4.0 只建立 persistence foundation。后续轮次：

1. **M4.1**: 实现 SQLite 版 MemoryRepository / SnapshotRepository，将生产 TurnPipeline 切换至 SQLite
2. **M4.2**: 实现 Conversation/Report metadata 恢复（重启后重建状态）
3. **M4.3**: 实现最近对话 API / 聊天搜索 API / 删除会话 API
4. **M4.4**: 实现 Restart/crash acceptance（E2E 验证重启后状态恢复）
5. **M5**: React + Vite 前端

M4.0 完成后不进入 M4.1、不开发 React、不开发 Docker、不开发 PostgreSQL、不开发 Remote MCP。

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

*最后更新：2026-08-18 | M4.0 — Local Persistence Architecture & Storage Foundation*