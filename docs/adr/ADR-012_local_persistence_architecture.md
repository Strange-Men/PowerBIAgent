# ADR-012: Local Persistence Architecture and Storage Foundation

- **状态：** accepted
- **日期：** 2026-08-18
- **决策者：** Strange-Men
- **背景：** M0–M3 所有记忆、快照和报表元数据均使用进程内存实现。服务重启后全部状态丢失。M4 需要建立持久化基础设施以支持会话恢复、搜索结果和 crash acceptance。
- **相关 ADR：** ADR-002（记忆系统设计）、ADR-005（TurnPipeline 控制面）、ADR-009（VerifiedFactSet）、ADR-010/011（Report Authority）

## 决策内容

### 1. 本地 MVP 持久化技术栈固定

- **数据库：** SQLite（嵌入式、零运维）
- **异步 ORM：** SQLAlchemy 2.0 Async（`sqlalchemy.ext.asyncio`）
- **异步驱动：** aiosqlite
- **迁移管理：** Alembic

### 2. 持久化包结构

新增 `backend/app/persistence/` 包，职责如下：

- `database.py`: AsyncEngine 生命周期、async_sessionmaker 工厂、SQLite URL 构建、PRAGMA 初始化（foreign_keys=ON, journal_mode=WAL, busy_timeout）
- `models.py`: SQLAlchemy ORM 持久化模型（非业务 domain model）
- `repositories/`: 待 M4.1 实现的 Repository 实现

### 3. 核心边界定义

数据库是 **persistence provider**，不是新的业务 authority：

- TurnPipeline / Memory commit rules 仍然是业务 authority
- Pydantic domain model ↔ SQLAlchemy row 转换在 Repository 层完成
- TurnPipeline 不得直接访问 SQLAlchemy Session
- 文件型 HTML 继续存储在 `local_state/reports/`，数据库只保存 metadata

### 4. JSON 序列化策略

结构化对象（StructuredWorkMemory payload、PendingClarificationContext payload、Snapshot payload）使用 JSON TEXT 列：

- Serialization: Pydantic `model_dump(mode="json")`
- Deserialization: Pydantic `model_validate()`
- 禁止：pickle、任意 Python object serialization、Secret 保存、原始 LLM response

### 5. 关键搜索字段分离

`request_id`、`conversation_id`、`runtime_mode`、`state_status`、版本号、时间戳等并发/搜索关键字段独立成列，不在 JSON 中嵌入。

### 6. 未来 PostgreSQL Migration Path

Repository 层通过 `MemoryRepository` / `SnapshotRepository` / `ReportRepository` ABC 抽象，SQLite 实现与未来 PostgreSQL 实现共用同一接口。迁移时只需新增 driver 适配层。

## 备选方案

| 方案 | 评估结果 |
|---|---|
| **SQLite + SQLAlchemy Async** | ✅ 选中。零运维、嵌入式、与 Python asyncio 配合良好、可迁移至 PostgreSQL |
| Docker + PostgreSQL | ❌ M4.0 不引入 Docker。开发环境复杂度过高，影响首次启动速度。MVP 阶段 SQLite 足够。PostgreSQL 可在产品化阶段再引入 |
| Redis | ❌ 本项目非高并发低延迟场景。Redis 增加运维复杂度，不符合 MVP 阶段需求 |
| SQLModel | ❌ SQLModel 在 SQLAlchemy 2.0 async 支持上不如原生 SQLAlchemy 成熟，且增加框架锁定风险 |
| DuckDB | ❌ 分析型数据库，不适合 MVP 的会话/记忆在线 OLTP 负载 |
| 纯文件 JSON + pickle | ❌ 不满足并发安全、查询、完整性约束和迁移需求 |

## 后果

### 正面

- 服务重启后状态可恢复
- Alembic 提供可版本管理的 schema 迁移
- SQLAlchemy Async 与 FastAPI asyncio 事件循环兼容
- Repository ABC 保持现有架构独立性
- JSON TEXT 列灵活支持结构化 payload，无需为每种类型建表
- SQLite WAL 模式允许读写并发
- 未来可平滑迁移到 PostgreSQL

### 负面

- M4.0 引入三个新依赖（SQLAlchemy、aiosqlite、alembic），增加安装体积
- SQLite 不适用于多进程写入场景（本项目为单进程 FastAPI，不受限）
- JSON TEXT 列无法在 SQLite 层做精确结构化查询（但搜索字段已独立成列，不影响）
- SQLite 不支持 PostgreSQL 的部分高级功能（array、full-text search 等），M4.3 搜索 API 需在应用层实现

### 架构约束

- M4.0 只建立 schema、migration 和抽象层，不将生产 TurnPipeline 切换至 SQLite
- M4.0 默认 `persistence_backend=memory`，SQLite 模式需显式启用
- 数据库文件位于 `local_state/persistence/powerbiagent.db`，不进入 Git
- UNIQUE(runtime_mode, request_id) 等数据库约束加强现有 domain invariant，不放宽

---

*最后更新：2026-08-18 | M4.0 Local Persistence Architecture*