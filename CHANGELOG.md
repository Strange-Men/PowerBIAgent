# CHANGELOG

> 完整历史变更记录见 `docs/archive/m0-m1.6_detailed_changelog.md`

## [M5.1] — 2026-08-21

### React 前端实现与核心联调

- 在 `frontend/` 正式创建 React 19 + Vite 8 + TypeScript 6 工程，新增 ESLint、Vitest、Testing Library、production build 与 Vite FastAPI proxy；`package-lock.json` 固定依赖，`npm audit` 为 0 vulnerabilities。
- 实现 GPT 式白色 AppShell、浅灰可折叠 Sidebar、新聊天欢迎态、已有对话滚动区、右侧用户消息、左侧自然 AI 正文、底部稳定 Composer 与基础窄屏适配。
- Composer 完成 "+"分组卡片与真实映射：数据模型 → `semantic_model_key`、报表模板 → `report_template_key`；无 discovery endpoint 时只使用 `src/config.ts` 集中配置，并在 UI 标记为本地配置。DeepSeek 选择器可展开/关闭、单选默认选中，不展示 Mock/GPT 或其他未接入模型。
- 新增 typed API client，接入 `POST /api/v1/chat`、recent/search/history/reports；严格携带 conversation `runtime_mode` 与 report `source_mode`。最近报表通过最近会话的 report history 组合；项目和账户不增加后端。
- Assistant adapter 按 answer/clarification/unsupported/error/empty/report 动态渲染；报表附件只接受与后端 `report_id` 一致的 canonical view/download reference。UI 不展示 Trace、tool sequence、execution audit、Memory、DAX、usage 或内部错误详情。
- 确认 M5.1 最小契约缺口：Chat/History 不暴露 QueryResult `columns/rows`、独立 metrics 或 ChartSpec。未修改 M0–M4 Snapshot/Persistence/Fact authority；前端不从 answer 或 audit 反解析、推导或伪造表格/图表。
- Fresh acceptance：frontend typecheck/lint/build PASS；Vitest `13 passed`；Chrome 1600×1000 欢迎态实际渲染检查 PASS；backend `1700 passed, 1 skipped`；Golden `11 passed, 1 manual-real skipped`；Architecture Gate `109`、Repository Safety、Error Ledger 与文档治理门通过。
- **M5.1.1（环境修复）：** 执行 `conda init powershell` 修复 Conda + PowerShell 激活问题，根因为从未初始化 conda PowerShell hook 导致 `conda activate` 后 Python 仍指向 base 环境。更新 `README.md` Quick Start 增加 Conda 初始化步骤、Python 路径验证、`No module named uvicorn` 与端口占用排查文档。更新 `docs/09_context_handoff.md` 增加本地启动说明节。未修改依赖、业务代码或 architecture gate 计数。
- M5.1 完成后停止；M5.2 NOT STARTED；不创建 Tag，不修改或合并 `main`。

**Settings.version:** M5.1

## [M5.0] — 2026-08-21

### 前端设计与契约固化

- M5.0 只修改 Markdown 文档，未创建 React/Vite 项目、package.json、src/、CSS、TS/TSX、Python 或 DB 代码。
- `frontend/README.md` 全面升级：从 M1.3.2 状态升级为 M5.0 文档，新增动态回答原则、左侧栏能力边界、"+“菜单映射原则、模型选择器 DeepSeek 唯一交互、后端能力到 UI 映射表、M5 路线三段、项目/账户仅展示。
- `docs/01_product_scope_and_frontend_skeleton.md` 全面重构：AI 回答动态渲染原则、Composer 结构、模型选择器交互、”“+”菜单映射、项目/账户仅展示、后端能力映射表、禁止固定内容序列。
- `docs/specs/10_frontend_visual_and_interaction_spec.md`：8.4 节完稿重写动态渲染规范（文字/指标/表格/图表/报表附件按需出现，非固定顺序）、模型选择器只显示 DeepSeek、后端能力到 UI 映射表、禁止固定内容序列、十八、禁止部分扩展内容固定禁止。
- `docs/specs/11_structured_answer_contract.md`：重写为动态渲染框架、新增 frontend rendering flow concept、ChatResponse 字段映射表、场景-展示对应表、删除 M1.4/M3 历史边界（已由 ADR 和后续轮次 supersede）。
- `docs/04_powerbi_mcp_and_api_contracts.md`：更新前端组合回答状态，确认 ChatResponse.report 已实现，统一 frontend envelope 不存在。
- `docs/07_milestones_status_and_open_questions.md`：补充 M5.0 已完成、M5.1/M5.2 待开始状态行。
- `docs/08_development_roadmap.md`：M5 拆分为 M5.0/M5.1/M5.2 三段路线。
- `docs/09_context_handoff.md`：更新为 M5.0 已完成状态，下一步为 M5.1。
- `README.md`：版本号同步为 M5.0，Project Status 增加 M5.0/M5.1/M5.2 行。
- 本轮不创建 Tag、不 Commit、不 Push。

**Settings.version:** 更新为 M5.0（与其余文档一致；版本字段随里程碑同步）

## [M4.4.2] — 2026-08-20

### M0–M4 Truth / Persistence Boundary Final Closure

- 移除 SQLite committed WorkMemory 的 partial column reconstruction fallback。Modern `payload_json` 现在是完整 domain reconstruction authority；NULL/empty、malformed JSON、缺少任一 `StructuredWorkMemory` 字段、Pydantic/domain validation failure 均 deterministic fail closed。
- Dedicated columns 只保留 query/index/integrity/support 职责；完整 payload 与 row 的 request/conversation/runtime/status/version/model/template/intent/failure integrity fields 不一致时拒绝恢复，禁止损坏 canonical filter/time/sort/top_n/last_query_plan 被静默清除。
- `MemoryRepository.get_latest_committed()` / `list_by_conversation()` 在 ABC、InMemory 与 SQLite 实现中将 `runtime_mode` 改为 mandatory；所有 production callers 显式传入 namespace，不再保留跨 Mock/Real aggregate 默认行为。
- 修复 InMemory 同 conversation_id + 同 request_id 跨 Mock/Real 时 conversation store 覆盖问题；内部 key 改为 `(runtime_mode, request_id)`，latest/list/get 均保持 namespace 隔离。
- 最终 boundary audit 额外收口两个 P1：非 legacy committed time state 的 process-local corruption 不再静默清空；terminal Snapshot payload 与 row 的 request/conversation/fingerprint/terminal fields 冲突时不再作为 replay authority。合法 legacy time string contract 保持不变。
- M0—M4 Semantic/DAX/Fact/Report/Memory/Snapshot/Namespace/Filesystem authority 模型保持不变；未增加产品功能，未进入 M5。无 schema change、无 Alembic migration。
- Fresh acceptance：targeted/adjacent `607 passed`；backend `1700 passed, 1 skipped`；Golden `11 passed, 1 manual-real skipped`；Architecture `109`、Repository Safety `239`、Error Ledger `25`、Documentation Governance PASS。Alembic head 保持 `c8d4e6f2a109`，fresh DB → head 与 head → head 幂等 upgrade PASS。

**Settings.version:** M4.4.2

## [M4.4.1] — 2026-08-20

### Memory Corruption Fail-Closed、README 重构与文档状态同步

- 修复 committed Memory canonical filter 的 fail-open：`StructuredWorkMemory` 在 domain construction/SQLite deserialize 时逐项按 `StructuredFilter` 验证，malformed payload 以稳定 `committed_memory_filter_invalid:<index>` 拒绝；storage 继续保持既有 `list[dict]` shape，合法历史 filter 不变。
- `StateTransitionService._previous_filters()` 不再捕获 malformed filter 后 `continue`；绕过初始 validation 的进程内损坏改为 `CommittedMemoryCorruptionError`，禁止清空、跳过或默认成“无筛选”。legacy time string compatibility 未扩大处理。
- TurnPipeline 将 committed/pending load、context build 与 controller setup 纳入既有 Owner abort 保护；corruption 异常会释放 process-local claim，同一 `request_id` 重试继续立即得到相同 fail-closed，而不是变成永久 waiter。
- 新增 StateTransition valid inheritance / Mock+Real corruption regressions，以及真实临时 SQLite dispose → fresh engine/repository/service restart regression。损坏 namespace 在 LLM、schema、DAX、Power BI 与新 Memory commit 前失败，memory version 不增长；合法 sibling namespace 正常恢复。
- 根 `README.md` 重构为长期 Landing Page：Overview、Highlights、How It Works、Truth Boundary、Current Capabilities、Quick Start、Runtime Modes、API、Persistence、Development & Validation、Project Status、Documentation、Scope / Known Limits。只保留有代码/fresh evidence 的能力，并明确 dedicated semantic-model/report-template discovery endpoint 当前未暴露。
- `AGENTS.md` 新增 README Maintenance Contract；正式 PRD 只同步实现状态；07/08/09 与本文件同步到 M4.4.1。无 schema change、无 Alembic migration；M5 NOT STARTED。
- Fresh acceptance：targeted corruption `5 passed`；邻近 Memory/StateTransition/persistence/restart `190 passed`；backend `1686 passed, 1 skipped`；Golden `11 passed, 1 manual-real skipped`；Architecture `109`、Repository Safety `239`、Error Ledger `25`、Documentation Governance 与 `git diff --check` PASS。Alembic head 保持 `c8d4e6f2a109`，fresh DB → head 与 head → head 幂等 upgrade 均通过。

**Settings.version:** M4.4.1

## [M4.4] — 2026-08-20

### 重启崩溃恢复验收与 M4 最终收口

- 新增 7 个 restart/crash integration tests，全部使用临时真实 SQLite 文件与 report filesystem，并在第一套 runtime/repository/service 写入后显式 dispose，再由全新 engine/session/repository/service 恢复；覆盖 committed Memory、terminal Snapshot replay/conflict、in-flight 丢失、report recovery/corruption、history/search/archive/delete 与 Mock/Real 同 ID 隔离。
- 明确 Snapshot crash semantics：terminal Snapshot 已保存但 process-local tracker 尚未 complete 时，重启后以 Snapshot 确定性重放且不执行工具；只有 process-local in-flight、没有 Snapshot 时不会凭空生成 completed。若同 request 已有任意 Memory 但缺 terminal Snapshot，则它是 incomplete crash witness，TurnPipeline abort 新 claim 并以 `IdempotencyCoordinationError` fail closed，不重执行可能已有外部副作用的请求，也不生成 terminal duplicate。
- 修复 report replay authority：新持久化 `ReportResultSnapshot` 只保存 report ID/reference/hash metadata，HTML 字段为空；重启重放通过既有 `ReportRepository.read_html()` 从 filesystem 读取，并严格核对 report metadata、request/conversation linkage、source mode 与 hash。严格验收同时发现并修复 adaptive Real report 路径构造了带 context 的 `ReportSpec` 却误传原对象的问题。missing/tampered HTML、corrupt metadata 或 linkage mismatch 均 fail closed；SQLite 不成为 HTML authority。旧 snapshot 中可能存在的 HTML 仅作兼容字段，配置了 report repository 时重放不会读取该值。
- 修复 M4.3 delete 的 DB commit → HTML unlink crash window：新增 durable `conversation_delete_intents` tombstone，在删除同 namespace DB state 的同一 SQLite transaction 内保存精确 report IDs 与删除计数；HTML cleanup 成功后才 finalize intent。unlink 失败、cleanup 后 finalize 失败或进程在两者之间退出时，全新实例以相同 `(runtime_mode, conversation_id)` 重试；pending intent 阻止该 namespace 被新 Memory/Snapshot/Report 写入复活。另一 namespace 不受影响。
- 新增 migration `c8d4e6f2a109`；fresh DB → head 与精确 M4.3 revision `f4c3a2b1907d` → head 均验证通过。没有尝试用 SQLite transaction 原子覆盖 filesystem。
- Fresh backend regression：`1681 passed, 1 skipped`；Golden `11 passed, 1 manual-real skipped`；Architecture Gate `109` Python files、Repository Safety `239` files、Error Ledger `25` entries、Documentation Governance 与 `git diff --check` 均 PASS。本轮 acceptance 不声称硬件掉电、filesystem/SQLite 自身违反 durability contract 或多进程/分布式事务保证；范围仍是 local single-machine MVP。Report create 对可观察的 metadata-save failure 继续 best-effort unlink，但未新增 durable create journal，因此不保证进程恰在 HTML rename 后、metadata commit 前退出时自动清除无引用文件；该窗口不会生成成功 metadata/Snapshot。
- **M4 FINAL PASS；M5 NOT STARTED。** 不创建 Tag，不进入 React/Vite、Remote MCP、PostgreSQL、Redis 或分布式事务。

**Settings.version:** M4.4

## [M4.3] — 2026-08-20

### 会话历史搜索与命名空间查询闭环

- 新增 `ConversationHistoryRepository` / `SQLiteConversationHistoryRepository` 与 application query service；recent/history/search/archive/delete 的每个 repository 方法强制接收 `runtime_mode`，report history 强制接收 `source_mode`，不存在只按 `conversation_id` 的查询入口。
- 新增 SQLite-only API：`GET /api/v1/conversations`、`GET /api/v1/conversations/search`、`GET .../{conversation_id}/history`、`GET .../{conversation_id}/reports`、`POST .../{conversation_id}/archive`、`DELETE .../{conversation_id}`；namespace 为必填 query parameter，page size 上限 50，opaque cursor 与查询/namespace/resource 绑定，非法 limit/cursor 显式 422。
- history authority 是 persisted `result_snapshots`；同 request 的 committed `work_memories` 仅补充结构化分析上下文，report history 复用 M4.2.3 strict metadata reconstruction。当前 schema 不保存逐字 user/assistant message transcript，因此 API 不声称或伪造 transcript，也不返回 snapshot 中的 report HTML、ORM row 或 `payload_json`。
- recent 按 `conversations.updated_at DESC, conversation_id ASC` 确定性排序；terminal snapshot 保存会在同一 transaction 内 touch exact `(runtime_mode, conversation_id)` root。archived conversation 默认不进入 recent/search，但仍可通过显式 namespace 读取 history/reports。
- search 使用普通 SQLite deterministic query，不引入 FTS5；只搜索 committed `work_memories.analysis_goal` 与 snapshot JSON 中显式的 `answer` / `clarification_question` / `unsupported_reason`，不搜索 report HTML、DAX、任意 payload 全文或未存储数据。
- archive 为幂等逻辑隐藏（`archived_at`）；delete 为同 namespace 物理删除，事务内删除 work memory、snapshot、pending clarification、同 source_mode report metadata 和 conversation root，随后由 `LocalReportRepository` 删除精确 report_id HTML。相同 conversation_id 的另一 namespace 不受影响。
- 新增 migration `f4c3a2b1907d`：`conversations.archived_at` 与 recent/history/report namespace 复合查询索引；fresh DB → head、现有 M4.2.3 revision `ab8d7df39a02` → head 均通过。
- 新增 20 个真实 SQLite/API tests；全仓 `1673 passed, 1 skipped`。M4.1/M4.2 persistence regressions `193 passed, 1 skipped`。
- M4.4 restart/crash acceptance NOT STARTED；未进入 React/Vite、Remote MCP、PostgreSQL、FTS5、vector/LLM search。

**Settings.version:** M4.3

## [M4.2.3] — 2026-08-20

### 持久化资源身份与元数据权威最终收口

- `payload_json` 是 modern metadata reconstruction authority，dedicated DB columns 是 immutable integrity witness；`ReportArtifactMetadata` 的 `report_id`、`template_key`、`semantic_model_key`、`schema_fingerprint`、`source_mode`、`content_hash`、`relative_path` 为 required persistence contract。payload 缺失或任一 row/payload 冲突均统一以 `ReportStorageError` fail closed，不再使用业务默认值或派生路径恢复。
- `conversation_id` / `request_id` 保持 nullable；DB linkage 有值时 payload 必须显式存在且一致。
- `report_id` 固定为 immutable resource identity；SQLite 与 InMemory 均只允许完整 metadata 相同的幂等 no-op，任一 metadata/provenance/linkage 不同均报 `report_artifact_identity_collision`，禁止 overwrite。
- `source_mode` 限定为 `mock | real`；未来 conversation report history 的确定性 namespace 固定为 `(source_mode, conversation_id)`，不得跨 Mock/Real 查询。
- 新增 30 个 corruption/identity/namespace tests，并修改旧 overwrite test 为 collision regression；全仓 1653 passed、1 skipped。
- 现有 `report_artifacts.source_mode` + `conversation_id` schema 已足够表达 namespace；不新增 Alembic migration，不创建空 migration。
- M4.2 series FINAL PASS；M4.3 NOT STARTED。

**Settings.version:** M4.2.3

## [M4.2.2] — 2026-08-19

### 路径与元数据一致性最终加固

**A — 路径 containment 加固（FIX 1）:**
- `_validate_path()` 替换 `str(target).startswith(str(root))` 为严格 `parent` 比较
- sibling-prefix escape 检测：`/x/reports_evil/` 不再被当作 `/x/reports/` 的子目录
- relative_path 必须是单层 filename（拒绝 nested directory）
- symlink escape 检测（platform 允许时）
- 新增测试：`../evil.html`、绝对路径、wrong filename、nested path、sibling-prefix escape、symlink escape、valid path

**B — 元数据 coherence 验证（FIX 2）:**
- 新增 `_validate_coherence()`：DB column vs payload_json 一致性验证
- 验证 9 个关键字段：report_id、template_key、semantic_model_key、schema_fingerprint、source_mode、content_hash、relative_path、conversation_id、request_id
- 任一冲突 → `ReportStorageError`，fail closed
- 新增测试：payload report_id != row、content_hash mismatch、relative_path mismatch、source_mode mismatch、linkage mismatch

**文档一致性:**
- `models.py` 修正 relative_path comment 为 `<report_id>.html`、payload_json comment 为 metadata-only
- `docs/09`：M4.2 series FINAL PASS，M4.3 NOT STARTED
- `docs/08`：更新路线状态

**Settings.version:** M4.2.2

**测试:**
- +16 tests for M4.2.2（8 path containment + 5 coherence + 3 legacy regression）
- 全仓 all passing

## [M4.2.1] — 2026-08-19

### 报表元数据权威边界与会话关联收口

**A — metadata-only serialization（payload_json 不再包含 HTML）:**
- 新增 `ReportArtifactMetadata` Pydantic DTO，排除 `html` 字段
- `payload_json` 序列化 metadata-only，HTML 只能通过 filesystem 加载
- 遗留 payload_json 包含 HTML → fail closed（`ReportStorageError`）
- 新增测试：直接读取 DB 确认 `<html` 不在 payload_json 中

**B — relative_path 成为正式 recovery authority:**
- `_validate_path()` 现在从 `artifact.relative_path` 定位 HTML 文件
- 路径安全规则：拒绝绝对路径、拒绝 `..` traversal、拒绝 resolve 越界、拒绝 wrong filename
- `relative_path` 存储简化为 `<report_id>.html`（不再含 `local_state/reports/` 前缀）
- 新增测试：注入 `../evil.html`、绝对路径、wrong filename 全部 fail closed

**C — conversation_id / request_id linkage 持久化:**
- `ReportRepository.store()` / `ReportArtifactRepository.save()` 扩展 `conversation_id` / `request_id` 参数
- `ReportSpec` 新增 `conversation_id` / `request_id` 可选字段
- DeepSeekTurnService / MockTurnService 在 render 前设置 linkage 到 ReportSpec
- 新增测试：linkage 写入 DB、重启后保持、双 conversation 隔离

**Settings.version:** M4.2.1

**测试:**
- 32 tests in test_m42_recovery.py（+9 new：5 strict path + 3 linkage + 1 legacy payload）
- 全仓 all passing

## [M4.2] — 2026-08-19

### 会话与报表元数据恢复

**Report metadata 持久化:**
- 新增 `ReportArtifactRepository` 抽象接口（`save()`/`get()`/`exists()`）
- `SQLiteReportArtifactRepository` 使用现有的 `report_artifacts` 表（无需 migration）
- `InMemoryReportArtifactRepository` 用于 memory backend 兼容
- HTML 正文继续存储在 filesystem，数据库不存 HTML blob
- 仅存储 metadata（template_key、content_hash、source_mode、relative_path 等）
- PK 碰撞由 DB primary key 约束保证

**LocalReportRepository metadata 集成:**
- 新增可选的 `metadata_repo` 参数注入
- `store()`：原子 filesystem 写入 → metadata repository 保存；metadata 失败时清理 HTML
- `get()`/`read_html()` 优先进程内缓存，miss 时通过 metadata repository 恢复（重启 recovery）
- `read_html()` 增加 `_validate_path()`：安全路径构建 + 文件存在 + content_hash 校验
- 缺失的 HTML 文件 → `ReportNotFoundError`
- 篡改的 HTML 文件（hash 不匹配） → `ReportStorageError`
- UUIDv4 碰撞由 DB PK 约束保证，无伪 async check

**Conversation/Snapshot 重启恢复（继承 M4.1 能力，新增验证）:**
- committed Memory 重启后 continuation
- PendingClarification 重启恢复
- Snapshot 重启后重放
- failed Memory 不进入恢复上下文
- Mock/Real namespace 重启后隔离

**Wiring:**
- `main.py` `_create_repos()` 扩展为 5 元组返回（含 `ReportArtifactRepository`）
- SQLite backend 复用同一 engine/session_factory
- Memory backend 使用 `InMemoryReportArtifactRepository`
- `report_repository` 创建移至 `_create_repos` 之后，接收 `metadata_repo`

**Settings.version:** M4.2

**新增文件:**
- `backend/app/persistence/repositories/report_artifact.py`

**测试:**
- 新增 `test_m42_recovery.py`：23 tests（report metadata save/get/restart/tamper/missing/unsafe 路径 + conversation restart + pending clarification restart + snapshot restart + Mock/Real isolation + wiring）
- 全仓 1618 tests passing（+23）

**注意:** 不新增 Alembic migration（report_artifacts 表现有 schema 足够）；默认 persistence_backend 仍为 memory。不进入 M4.3 history/search/delete API。

## [M4.1.3] — 2026-08-19

### SQLite Lock Transaction Exit Final Hardening

**Fix A — locked failure 必须退出原 transaction 再 fresh-session resolution:**
- M4.1.2 的 `_resolve_locked_commit_failure` 虽创建新 session，但在 `async with session.begin()` 异常处理器内部被调用，原 transaction context 尚未退出
- 重构：捕获 locked OperationalError 后只保存 failure context → session.begin() context 自然退出/rollback → transaction 外使用全新 session 调用 resolver
- 成功路径完全不变，全部在单一 transaction 内

**Fix B — 真实 SQLite lock integration test:**
- `create_engine` 新增可选的 `busy_timeout` 参数（测试 100ms，production 5000ms）
- 3 个新测试：real 2-engine SQLite lock 触发 locked path、pre-created pending 下 lock 测试、instrumented session-exit 顺序证明
- 不依赖 sleep-based 同步，使用明确的 connection/tx 生命周期控制

**Error Handling 结构硬化（M4.1.3 最终版）:**
- IntegrityError：仅 committed-version unique conflict → `MemoryVersionConflictError`；其他 IntegrityError 原样抛出
- OperationalError A（locked/busy）：transaction 内只保存上下文 → transaction 完全退出/rollback → transaction 外 fresh session bounded reread
- OperationalError B（non-lock：disk I/O、corruption）：→ `PersistenceRepositoryError`

**M4.1 series FINAL PASS:**
- M4.1: SQLite Memory/Snapshot persistence + production wiring + restart proof
- M4.1.1: conversation root race hardening + narrowed error semantics
- M4.1.2: fresh-session resolver + real OperationalError injection
- M4.1.3: transaction-exit-before-reread + real SQLite lock integration

**Settings.version:** M4.1.3
**测试:** 63 persistence tests passing（+3）
**注意:** 不新增 Alembic migration（schema 未变）；默认 persistence_backend 仍为 memory。M4.2 未开始。

## [M4.1.2] — 2026-08-19

### SQLite Transaction Failure & Error Semantics Hardening

**Fix A — Locked transaction 内不继续查询:**
- 原 `commit()` 在捕获 `OperationalError("database is locked")` 后在同一 session/transaction 中继续查询 latest version，但 transaction 在 OperationalError 后可能已进入 failed state
- 抽取 `_resolve_locked_commit_failure` helper 至 `repositories/common.py`，使用 fresh session + fresh transaction 重新读取 latest committed version
- `commit()` 中 locked 分支简化为 delegate，不再在 failed transaction 中 query

**Fix B — 真实 OperationalError 注入测试:**
- 通过 `unittest.mock.patch.object(AsyncSession, 'execute')` 在 UPDATE 语句层级注入真实 OperationalError
- 6 个新测试覆盖：non-lock → PersistenceRepositoryError、locked + version advanced → MemoryVersionConflictError、locked + unchanged → PersistenceRepositoryError、fresh-session proof（≥2 distinct sessions）、failed tx recovery、no half-committed memory

**Error Handling 结构硬化:**
- IntegrityError：仅 committed-version unique conflict → `MemoryVersionConflictError`；其他 IntegrityError 原样抛出
- OperationalError A（locked/busy）：退出原 transaction → fresh session bounded reread → 版本冲突或持久化失败
- OperationalError B（non-lock：disk I/O、corruption、unable to open DB）：→ `PersistenceRepositoryError`

**测试:**
- 新增 6 个真实 error injection tests
- 全仓 1574 tests passing（+6）
- Golden 11 PASS / 1 SKIP

**注意：** Settings.version 保持 `M4.1`（frozen field，非功能版本号）；不新增 Alembic migration（schema 未变）；默认 persistence_backend 仍为 memory。M4.2 未开始。

## [M4.1] — 2026-08-18

### SQLite 记忆与请求快照持久化 + 并发提交 invariant

**Production wiring:**
- `main.py` 中 `MockTurnService` 和 `DeepSeekTurnService` 现在正确注入 `snapshot_store` 参数（之前 SQLite 模式下为 `None`）
- `persistence_backend=sqlite` → 使用 `SQLiteMemoryRepository` + `SQLiteSnapshotRepository`
- `persistence_backend=memory` → 使用 `InMemoryMemoryRepository` + `ResultSnapshotStore`（默认）

**DB 级 concurrent commit invariant:**
- 新增 partial unique index `ix_work_memories_committed_version`：`UNIQUE(runtime_mode, conversation_id, memory_version) WHERE state_status = 'committed'`
- 确保同一 (runtime_mode, conversation_id, memory_version) 最多只有一个 COMMITTED 行
- `commit()` 内捕捉 `IntegrityError`/`OperationalError` 转换为 `MemoryVersionConflictError`
- 新增 corrective migration `ab8d7df39a02`

**严格并发测试：**
- 旧测试 `len(successes) >= 1` → 严格 `assert len(successes) == 1 and len(conflicts) == 1`
- 8 轮多轮并发验证（against SQLite WAL mode race）

**测试：**
- 新增 3 个 wiring 测试（SQLite snapshot injection、memory ResultSnapshotStore default、restart recovery via wiring）
- 新增 2 个严格 concurrent commit 测试（single-round + 8-round multi-round）
- 全仓 1559 tests passing

**注意：** `persistence_backend` 默认仍为 `memory`，`sqlite` 提供跨重启持久化。M4.2 未开始。

### M4.1.1 — 会话创建竞态与数据库错误语义加固（本轮）

**Fix A — Transaction-safe conversation root upsert:**
- 抽取共享 `ensure_conversation` helper 至 `repositories/common.py`，使用 `INSERT OR IGNORE` 替代原 `SELECT → INSERT → catch IntegrityError → expunge`
- MemoryRepository 和 SnapshotRepository 均委托该共享 helper，消除两处重复逻辑
- 解决 flush IntegrityError 后 SQLAlchemy transaction 可能进入 failed state 的问题

**Fix B — 缩窄数据库错误语义映射:**
- `IntegrityError` 仅当确认来自 committed-version partial unique index 才转 `MemoryVersionConflictError`；其他 IntegrityError（FK、NOT NULL）re-raise
- `OperationalError` 区分 SQLite busy/locked 条件 vs 磁盘 I/O、损坏等非锁错误；非锁错误转 `PersistenceRepositoryError`；锁冲突时 bounded re-read 最新版本再决定错误类型
- 新增 `PersistenceRepositoryError` 异常类（最小异常体系）

**新增测试（9 个）：**
- 4 个 conversation first-create race tests（双 session 并发创建、Memory/Snapshot 交叉创建、8 轮多轮、串行幂等）
- 5 个 error semantics tests（committed conflict、unrelated IntegrityError、_is_sqlite_locked detection、_is_version_index_conflict detection、failed tx recovery）

**测试：**
- 全仓 1568 tests passing（+9）
- Golden 11 PASS / 1 SKIP

**注意：** Settings.version 保持 `M4.1`（frozen field，非功能版本号）；不新增 Alembic migration；默认 persistence_backend 仍为 memory。

### SQLite 记忆与请求快照持久化 + 并发提交 invariant

**Production wiring:**
- `main.py` 中 `MockTurnService` 和 `DeepSeekTurnService` 现在正确注入 `snapshot_store` 参数（之前 SQLite 模式下为 `None`）
- `persistence_backend=sqlite` → 使用 `SQLiteMemoryRepository` + `SQLiteSnapshotRepository`
- `persistence_backend=memory` → 使用 `InMemoryMemoryRepository` + `ResultSnapshotStore`（默认）

**DB 级 concurrent commit invariant:**
- 新增 partial unique index `ix_work_memories_committed_version`：`UNIQUE(runtime_mode, conversation_id, memory_version) WHERE state_status = 'committed'`
- 确保同一 (runtime_mode, conversation_id, memory_version) 最多只有一个 COMMITTED 行
- `commit()` 内捕捉 `IntegrityError`/`OperationalError` 转换为 `MemoryVersionConflictError`
- 新增 corrective migration `ab8d7df39a02`

**严格并发测试：**
- 旧测试 `len(successes) >= 1` → 严格 `assert len(successes) == 1 and len(conflicts) == 1`
- 8 轮多轮并发验证（against SQLite WAL mode race）

**测试：**
- 新增 3 个 wiring 测试（SQLite snapshot injection、memory ResultSnapshotStore default、restart recovery via wiring）
- 新增 2 个严格 concurrent commit 测试（single-round + 8-round multi-round）
- 全仓 1559 tests passing

**注意：** `persistence_backend` 默认仍为 `memory`，`sqlite` 提供跨重启持久化。M4.2 未开始。

## [M4.0] — 2026-08-18

### 本地持久化架构与存储基础

**新增：**
- ADR-012：本地持久化架构决策（SQLite + SQLAlchemy Async + aiosqlite + Alembic）
- backend/app/persistence/ 包：database.py、models.py、serialization.py
- 数据库 schema 设计（conversations / work_memories / pending_clarifications / result_snapshots / report_artifacts）
- Alembic 迁移初始化（backend/alembic/）
- Settings 扩展：PersistenceBackend、persistence_database_path
- Repository 抽象清理：TurnPipeline → MemoryRepository、新增 SnapshotRepository ABC
- 序列化策略：Pydantic model_dump(mode="json") → JSON TEXT → model_validate()
- PRAGMA 配置：foreign_keys=ON、journal_mode=WAL、busy_timeout=5000
- UNIQUE(runtime_mode, request_id) 数据库约束

**依赖新增：**
- sqlalchemy==2.0.52
- aiosqlite==0.22.1
- alembic==1.19.1

**测试：**
- 26 个持久化基础设施测试（engine/Alembic/ABC/serialization/constraints/PRAGMA）
- 全仓 1503 tests passing（1477 + 26）

### M4.0 Corrective Hardening — 2026-08-18

**CI 修复：**
- pytest-asyncio async fixture 兼容性修复：`@pytest.fixture` → `@pytest_asyncio.fixture`

**Schema 加固：**
- conversations 表 PK 从单列 `(conversation_id)` 改为复合 `(runtime_mode, conversation_id)`，实现 Mock/Real 命名空间隔离
- work_memories、result_snapshots、pending_clarifications 的外键改为复合 FK `(runtime_mode, conversation_id)` 引用 conversations，防止跨命名空间错误关联
- 新增 corrective migration `01dc0d90d920`（无历史改写）

**PRAGMA 修复：**
- foreign_keys=ON 和 busy_timeout=5000 现在通过 SQLAlchemy 连接池事件在每个新 DBAPI 连接上设置（不再只配置第一个连接）
- journal_mode=WAL 保持在 configure_engine() 中（数据库级别，持久化）

**测试新增（14 tests）：**
- 5 个 migration 约束验证测试（复合 PK/FK、initial→head 升级）
- 2 个 conversation 命名空间测试（同 conv_id 不同 mode 允许、同 mode 拒绝重复）
- 4 个复合 FK 隔离测试（cross-namespace 拒绝、same-namespace 通过）
- 3 个 PRAGMA 每连接测试（单引擎多连接、独立双引擎）
- 全仓 1517 tests passing

**注意：** M4.0 只建立 persistence foundation。生产 Memory / Snapshot 仍未正式切换 SQLite（属于 M4.1）。

## [M3.4] — 2026-08-17

### 自适应报表规划与可视化策略

- 根因修复：M3.3 仍是"固定四查询、固定两种横条"，无法根据自然语言与语义模型能力生成不同报表；M3.4 修复**报表规划能力**，不只是 HTML/CSS
- 新增 ADR-011：固定模板 = 固定设计规则 + 允许能力目录（Design System / Allowed Section Catalog / Visualization / Layout / Theme / Security），不是固定输出内容；ADR-010 固定事实安全边界继续有效，"一个 template 永久绑定一个 fingerprint + 固定四 queries"限制被 supersede；contract version 升至 2.0
- `capability.py` 重构为真实 schema-aware capability engine：9 个 registry-owned sections（SALES_KPI / QUANTITY_KPI / ORDERS_KPI / AOV_KPI / TIME_TREND / CATEGORY_CONTRIBUTION / REGION_COMPARISON / TOP_PRODUCTS / TOP_CUSTOMERS）；三层门控（TemplateContract 声明 + runtime schema 对象与类型 + 已验证非空事实）；缺能力 fail closed，绝不 Mock/占位/空图
- 新增受控 Report Intent weak signal：LLM 只输出 registry-owned section ID；未知/非法 ID 丢弃；确定性 NL 匹配器是地板；"只看…"忽略 LLM 增量；单独计数 `llm_report_intent_call_count`，与事实类计数分开
- 新增 deterministic ReportPlan / ReportPlanner：requested / resolved / unavailable sections、去重 query requirements、provenance；用户没要求的 section 不查询；零可解析 section fail closed
- 新增 VisualizationPolicy（KPI Card / Line / Donut≤8 / Column / HBar，禁止所有 grouped→horizontal bar）、LayoutPolicy（KPI 行 → 全宽趋势 → 2 列对比/排行对）、ThemePolicy（dataviz 验证 8 色 categorical 固定顺序 + blue sequential、系统字体、间距 token）
- `SalesReportRenderer`（原 FixedSalesReportRenderer 更名）支持 charts：KPI cards、inline SVG line/donut、CSS column/hbar；无 JS/CDN/外部资源；空 section 不输出；同一业务事实不重复展示
- 时间趋势真实链：Power BI query → QueryResult → VerifiedFactSet；Renderer 不聚合；已验证时间点仅确定性显示排序（不创造新业务数值）；复用现有 DeterministicDAXBuilder，无第二 DAX builder
- 最小通用扩展：`CanonicalQueryPlan.dimension_tables` / `dimension_order`（star-schema 重名列消歧，None 时 M2 行为不变），DeterministicDAXBuilder / Layer 2 / RestrictedDAXVerifier 同步支持；ChartSpec 增加结构化 `visual_type` / `business_role` / `series` / `layout_hint`
- 测试矩阵：Simple/Rich/synthetic 三模型；5 个 NL cases（只看销售额 / 看看销售趋势 / 按区域看销售表现 / 看看头部客户 / 生成完整销售分析报表）；LLM weak-signal 边界；fact-gate 空结果 drop；全部 anti-fake 回归保留
- Real acceptance（双模型）：Simple PBIX 完整请求解析 4 sections / 4 查询（M3 基线行为不变）；Rich PBIX（fingerprint `31505f7987133c235554bc00e7ca5ce3fd42351b08e984c0c011f48410e56157`）解析 9 sections / 9 真实查询（15 个月度趋势点、3 品类、4 区域、Top 5 产品/客户），4 种 visual；source real；DAX/ReportData/Report factual/Renderer LLM calls 与 fallback/fake QueryResult 全 0
- Fresh acceptance：backend 1477 passed、Golden 11 PASS / 1 manual skip、Architecture / Repository Safety / Error Ledger / Documentation Governance / diff check 全部 PASS；桌面与 430px 截图已产出，程序化 DOM/几何检查 PASS，最终视觉验收用户人工确认 PASS。

---

## [M3.3] — 2026-08-17

### 销售报表模板V2与能力驱动布局

- 新增 `backend/app/report/capability.py`：SectionCapability 概念基于 runtime schema + TemplateContract + VerifiedFactSet 确定性判断 section 是否可渲染；SALES_KPI、CATEGORY_BREAKDOWN、TOP_PRODUCTS 三个正式 section；TIME_TREND / REGION_BREAKDOWN / CUSTOMER_BREAKDOWN 为纯 extension point，无 contract/facts 时自动 UNAVAILABLE，绝不生成占位或伪造内容
- `FixedSalesReportRenderer` 改为 section-capability 感知渲染：每 section 只保留一种主要视觉表达（horizontal bar），移除与 bars 重复的同源明细 table；KPI、Category bars、Top Product bars 各回答独立业务问题；缺失 section 自动 fail closed 不输出
- `sales_report.html` 模板重写：简化为双列 KPI → 品类 bars → 产品 bars → metadata footer；响应式窄屏 Flex 换行；无 JS/CDN/外部资源；无 `<table>` / 重复数据区域
- 新增多语义模型防伪测试：Model A 当前简单 schema 所有 section 正常；Model B 多 Date/Region/Customer 字段不自动生成新 section；Model C 缺 Category/Product 时 contract validation fail closed；anti-fake 验证 production 代码无 oracle、无 LLM/PowerBI authority
- 新增回归测试：no duplicate table visual regression、section capability evidence gates、extension point 不自动激活
- Fresh acceptance：backend 1445 passed、harness 11/12 PASS (1 skip)、Architecture/Repository Safety/Error Ledger/Documentation Governance/diff check 全部 PASS

## [M3.2] — 2026-08-17

### 销售报表最终可视化加固与 M3 收口

- M3.1 commit `fa4cc0c97a10bcc0867c414dc3fa2d7fa9b35e57` 经 GPT 远程审计后从 M3.0 纯 fast-forward 合入 `main`；`PowerBIAgent Validation` run `31989328261` 对应同一 main push SHA，结论 success，随后安全删除本地与远程开发分支
- `FixedSalesReportRenderer` 直接从已校验的 Category / Top Product rows 生成确定性 CSS 横条；宽度按同组绝对最大值归一化并固定半入舍入到两位小数，横条旁保留真实值与同源明细表，不增加查询、排名、趋势、因果或业务事实
- 固定模板完成桌面与窄屏层级、KPI、横条、表格和弱化 metadata 加固；窄屏横条使用稳定 Flex 换行，无 JavaScript、CDN、外部库、网络请求或自由 HTML
- Renderer / Repository 保存前额外拒绝 `link`、`iframe`、`object`、`embed`、`@import`、CSS `url()` 与 `src=`；Intent / QueryPlan prompt 明确 DeepSeek 仅提供弱语言信号，无模板、查询、KPI、图表事实、HTML/CSS、布局、保存路径或资源引用 authority
- M3 PBIX Real acceptance 通过：fingerprint `d72c9dd04fcda216ffa421d84e85c01d9643e2c2db133d1661639970eb6b11ac`，四查询非空，Total Sales `500821`、Total Quantity `358`，source real，fallback/fake QueryResult 与 DAX/ReportData/Report factual/Renderer LLM calls 全为 0，view/download 200，受管 HTML 与验收副本逐字节一致
- 最终受管 HTML 为 10,230 bytes，SHA-256 `7144438843fae9a626e6122f4b936a2ff3fe2d973dc85c6e20c644f2ede6578d`；以禁止网络/脚本的静态 Renderer 实际渲染后，桌面与 430px 窄屏视觉验收均 PASS
- Fresh acceptance：prompt/report targeted 112、report/contract/API targeted 96、backend 1435、Golden 11 PASS/1 manual Real skip、Architecture 89、Repository Safety 198、Error Ledger 25、Documentation Governance 与 diff check 全部通过
- M3 最终收口；不提交 PBIX/HTML/`local_state/`，不进入 M4/M5 或 Remote MCP，不创建 Tag

## [M3.1] — 2026-08-17

### 销售报表生成与 HTML 资源闭环

- M3.0 commit `e4b5c6c6a759cdf22c74c4d87902482563e27cad` 经 GPT 远程审计 PASS 后纯 fast-forward 合入 `main`；`PowerBIAgent Validation` run `31986207118` 对应 main push 与同一 SHA，结论 success
- `sales_report` 固定四查询继续逐项复用 CanonicalQueryPlan → Deterministic DAX → Independent Layer 3 → ToolGateway → PowerBIAdapter → QueryResult → VerifiedFactSet；无第二 Power BI、DAX、Fact、TurnPipeline 或 Memory 控制面
- 新增 deterministic `SalesReportData` 与唯一固定 `ReportSpec`；KPI、Category rows、Top Product 结果位置与全部 provenance 只来自四组 QueryResult / VerifiedFactSet，任一缺失、错绑、伪造、空结果、mixed source 或 fingerprint mismatch 均 fail closed
- 新增 `FixedSalesReportRenderer` 与固定 UTF-8 `sales_report.html`；静态 HTML 无 JavaScript、外部脚本/CDN 或自由用户 HTML，所有动态文本安全转义
- 新增 `ReportArtifact`、原子 `LocalReportRepository`、`GET /api/reports/{report_id}` 与 `/download`；report_id 只由后端生成，路径遍历与 unknown ID 拒绝，幂等 replay 复用同一 artifact
- Real acceptance 使用 M3 PBIX 完成 4 queries → 4 QueryResult → 4 VerifiedFactSet → SalesReportData → ReportSpec → Renderer → ReportArtifact；Total Sales / Total Quantity oracle 匹配、source real、view/download 200、保存内容 hash 一致，DAX/ReportData/Report factual/Renderer LLM authority 与 fallback/fake QueryResult 均为 0
- 本轮不进入 M4/M5 或 Remote MCP，不新增 M3.2 功能，不提交 PBIX/HTML/local_state，不合并 main，不创建 Tag

## [M3.0] — 2026-08-17

### 销售报表合同与开发路线固化

- M0—M2 已由 Tag `m2.6.4-m0-m2-final-seal` 在 `70748da` 正式封板；M3 从该 clean main 基线开始
- M3 MVP 唯一 production template 固化为 `sales_report`；历史 `sales_weekly` / `satisfaction` / `operating_overview` 保留识别但 production availability=false
- 新增 TemplateContract、M3 PBIX model/schema fingerprint binding、fail-closed compatibility validator 与四查询 ReportDataPlan；ReportDataPlan 不消费 LLM draft、QueryResult 或 Known-answer expected
- 四个固定 sub-query 继续复用 CanonicalQueryPlan → Deterministic DAX → Independent Layer 3 → ToolGateway → Local MCP → QueryResult → VerifiedFactSet，没有第二 Power BI/DAX/Fact pipeline
- 新增 ADR-010 与 `sales_report_contract_smoke.py`；M3 专用 PBIX 已验证 runtime schema、四个真实查询、scalar local oracle、`source_mode=real`、fallback/LLM/Renderer 调用均为 0
- Fresh acceptance：targeted 19、backend 1412、Golden 11 PASS/1 manual Real skip、Architecture 86、Repository Safety 193、Error Ledger 25、Documentation Governance 与 diff check 全部通过
- 本轮未实现正式 Renderer、HTML 文件、report resource repository、查看/下载 API，未进入 M3.1/M3.2/M4/M5，未创建 Tag

---

## [M2.6.4] — 2026-08-14

### M0—M2 最终加固与文档治理

- TopN facts 改为显式 `result_position` / QueryResult order，ties 与 truncated 结果不再生成严格 business rank；保持 boundary ties 可超过 N
- Bounded semantic selector 增加 Catalog metadata evidence shortlist 与 post-validation；未知、证据并列、非法 ID 或选择冲突均 fail closed
- data/report-shaped `UNSUPPORTED` 进入 authoritative Grounding/capability check；明确 out-of-scope 请求保持 early-stop，失败不污染 Pending/Committed Memory
- 补齐 approved 数量问法 alias；Real acceptance 观察器直接核对 ToolGateway DAX、fact-bounded output、TopN/tie safety 与 DAX/Answer LLM 零调用
- 恢复 AGENTS/README/00/03/04/05/07/08/09/CHANGELOG 真实性，建立 `docs/index.md`、specs/milestones/archive 分层与 deterministic Documentation Governance Gate
- 完成 M0—M2 fresh offline/Real hardened acceptance 与远程核心审计；长期文档已对齐 Semantic Grounding、Deterministic DAX、VerifiedFactSet 和 Pending/Committed 边界；未创建 Final Tag

---

## [M2.6.3] — 2026-08-14

### Deterministic Execution & Verified Facts

- Real Canonical QueryPlan 只经 Deterministic DAX Builder；Independent Layer 3 独立验证 exact group-by、EQ/time、TopN/ORDER BY 与无额外业务语义，Real DAX LLM calls=0
- 建立 VerifiedFactSet factual authority，Answer/Report 只消费可追溯的数字、结果顺序、极值、筛选、时间、rows 与 provenance
- PendingClarificationContext 与 committed Memory 分离，partial clarification 完整后才执行并在全链成功后提交
- 正式多轮 contract 更正为 6 Conversation / 16 Turn，禁止从欠指定 ranking 默认 Product；`dax_unplanned_group_by_dimension` 与 `dax_filter_structure_not_verifiable` 收口为 0

---

## [M2.6.2] — 2026-08-13

### Business Semantic Grounding

- 建立 model-scoped Business Semantic Catalog，并以 friendly model key + runtime schema fingerprint 绑定
- Grounding 成为 Measure/Dimension/Filter Field/runtime Member/Time 的 canonical authority；Intent/QueryPlan LLM 只保留 weak signal
- 结构化 semantic slot 状态与 deterministic StateTransition 支持 KEEP/REPLACE/CLEAR 及 Filter ADD/REPLACE/REMOVE
- Canonical QueryPlan 只能消费 runtime schema、approved glossary、bounded member values 与固定时间边界；歧义或未解析必须 clarification

---

## [M2.6.1] — 2026-08-12

### Known-answer 独立数值 Oracle 与多轮 Harness 固化

- 在 Harness/Test 边界新增独立 Known-answer Oracle，Expected 只从显式 baseline 读取，不依赖 LLM、当前 DAX、Answer 或 Actual QueryResult 反向生成
- 支持 scalar、按业务 Key canonicalize 的 grouped rows，以及校验顺序并允许第 N 名 ties 超过 N 行的 ordered/TopN；数值默认绝对/相对容差均为 `1e-9`，并限制可配置上限
- 固化 8 个 Known-answer Case（含 2 个 holdout）和 6 组、15 Turn 的 Power BI 多轮 MiniSuite；Conversation 只有所有 Turn 全部 PASS 才成功
- 唯一 M2.6.1 Runner 通过正式 Chat API 在 Fake/Mock 模式验证 Filter refinement、Dimension switch、Filter replacement、Metric switch、Clarification 与失败 Turn Memory 完整性
- 真实 expected baseline 仅允许位于 Git 忽略的 `local_state/`；缺失或覆盖不完整时明确失败，不回退 committed fictional example baseline
- 修复 Harness module docstring 的 invalid escape warning，并更新 `ChatResponse.powerbi_mode` 描述为 `mock / local_mcp / remote_mcp（Deferred）`
- 本轮真实 DeepSeek、Local MCP 与 Power BI Desktop 调用均为 0；未修改 TurnPipeline、ValidationService、Architecture Gate 或 `local_mcp.py`，M2.6.2 真实验收仍未执行

---

## [M2.6] — 2026-08-12

### 数据问答正确性契约与架构治理加固

- Filter Layer 3 对可确定验证的 `eq` 检查 field/operator/value，并拒绝额外业务 Filter；Real 路径其余 Operator 明确为 `NOT_VERIFIED`，Mock 兼容路径不变
- TopN 验证 N、单一 Measure 与方向；显式 sort 另要求查询末尾 `ORDER BY`，不再以 `row_count <= top_n` 否定合法 ties
- Architecture Gate 升级为 AST + ownership：MCP SDK/raw call、ToolGateway、平行生产控制面、Provider 反向依赖与禁用框架均进入 CI 门禁
- Health 保留 `ready` 兼容字段，新增 `configuration_ready` 与 `powerbi_live_connected=false`，不把配置就绪描述为 Desktop 实时在线
- 冻结 `local_mcp.py` 的 Provider / protocol Adapter 职责；本轮未修改其业务逻辑，未调用 DeepSeek、Local MCP 或 Desktop
- 仅固化 M2.6.1 Known-answer Oracle 与 Real Multi-turn Harness 成功契约；未实现后续验收

---

## [M2.5] — 2026-08-12

### 真实业务 Golden 回归验收与 M2 封板

- 新增唯一 M2 Business Golden 人工 Smoke，通过正式 Chat API 完成 7 个真实 Case，覆盖 Measure、Dimension、Filter、Top N/Sort 与 3 个未在 Prompt 点名的对象/组合
- 将 `gc_012_real_baseline` 固化为 Local Desktop 人工真实基线，通用 CI 继续只使用 Mock/Fake，不接 Desktop、PBIX、DeepSeek 或 Microsoft 凭据
- 20 类关键 Bad Case、Answer provenance、Replay、Real 不回退 Mock、M0—M1 Golden 与 Mock 全量回归通过
- ValidationService 生产代码变化为 0，未新增完整 DAX Parser、业务词典、Pipeline、Service 或 Provider；现有 Prompt 无需为 Golden 增加固定答案
- Remote MCP 生产化继续 Deferred；M2 能力限定为 Local MCP + Power BI Desktop Demo，下一阶段为 M3 固定模板报表正式渲染

---

## [M2.4] — 2026-08-11

### 现有 TurnPipeline 接入真实 Power BI

- 将 `LocalMCPPowerBIAdapter` 作为 Provider 注入既有 DeepSeekTurnService / TurnPipeline / ToolGateway，没有复制 Service、Pipeline 或工具网关
- 落地真实 Schema 驱动的 QueryPlan Semantic Validation，以及 Measure/Dimension/Filter、group-by 和 `SUMMARIZECOLUMNS` 参数顺序的确定性 Layer 3 校验
- 将 `source_mode=real` 传播到 Turn、Answer/Report、Snapshot、Replay 与 Trace；幂等 Replay 不重复执行 DeepSeek 或 Power BI
- 真实跑通总销售额、总数量和带类别过滤的销售额三个自然语言 Case；Answer provenance 严格引用 QueryResult.columns
- 保持 Real 失败不回退 Mock、Remote Deferred、Issue #124 Open；修复 stdio 异常组掩盖既有 DAX 错误分类的问题

---

## [M2.3] — 2026-08-11

### 真实 DAX 执行与 QueryResult 标准化

- 在既有 ToolGateway → PowerBIAdapter → Local MCP 边界内，以单次只读 stdio/Desktop 会话调用 `dax_query_operations` 的 `Execute`
- 依据 beta.12 实机 schema 使用 `resultMode=Inline`，标准化有序 columns、二维 rows、实际 row_count、execution time、request_id、`source_mode=real` 与 truncated
- 新增 DAX、timeout、permission、connection、malformed、MCP protocol、oversized 与 Preview row-data missing 错误分类；仅 NETWORK 最多重试一次，Real 不回退 Mock
- 新增 Fake MCP 回归与脱敏人工 DAX Smoke；固定 ROW 值 1 及 `Total Sales` / `Total Quantity` 实际数值均验证成功
- 当前实机未复现仍为 Open 的 Issue #124；未调用 DeepSeek、未接完整 Chat、未修改 TurnPipeline / DeepSeekTurnService / main / routes

---

## [M2.2] — 2026-08-11

### 真实 Semantic Model Schema 接入

- 保留公开可复现的 Local MCP 实机固定版本 `0.5.0-beta.12`，并用 npm 官方 Registry 与隔离缓存复核
- 在既有 ToolGateway → PowerBIAdapter → Local MCP 边界内，以单次只读会话调用五类 Schema 工具的 `List` / `Get`
- 将真实 Table、Column、Measure、Relationship 与 Hierarchy 映射为向后兼容的 `SemanticModelSchema`，保留 Measure expression、数据类型与基础关系语义
- 新增 Fake MCP 回归与脱敏人工 Schema Smoke；真实验收为 3 tables、19 columns、2 measures、1 relationship、2 hierarchies
- `Total Sales` 与 `Total Quantity` 已准确识别为 Measure；未执行 DAX、未调用 DeepSeek、未接完整 Chat、未修改 TurnPipeline

---

## [M2.1] — 2026-08-11

### Local Power BI MCP 最小真实连接验证

- 经用户批准将当前 Demo 验证路径从受管理员前置条件阻塞的 Remote MCP 调整为 Local MCP + Power BI Desktop；Remote 不是失败，ADR-006 生产化路线完整保留
- 新增 accepted ADR-007 与统一 M2 Local Demo / Remote Production 计划
- 引入官方 `mcp==2.0.0`，新增只读 stdio Local Adapter、脱敏连接诊断与人工 Smoke
- 真实验证 `@microsoft/powerbi-modeling-mcp@0.5.0-beta.12` 启动、协议 `2025-11-25`、21 个工具发现以及 Power BI Desktop 连接
- 保留并泛化 Semantic Grounding 与 DAX 业务语义四层验收契约
- M2.1 不读取完整 Schema、不执行 DAX、不调用 DeepSeek、不接 Chat

---

## [M2.0] — 2026-08-11

### 真实 Power BI Remote MCP 接入规划与开发路线固化

- 修复 AGENTS / CLAUDE 冷启动遗漏 Error Ledger 的治理矛盾
- 将 ADR-005 从 ADR 索引拆分为正式独立文件
- 基于 Microsoft 与 MCP 官方资料复核 Remote MCP、OAuth、权限与 Python SDK
- 新增 accepted ADR-006，固化 Adapter、ToolGateway、OAuth、工具白名单与失败边界
- 固化 M2.1—M2.5 开发路线、防偏移门禁和离线 CI / 人工 Smoke 边界
- 生产业务逻辑变化为 0；真实 LLM 调用为 0；真实 Power BI 调用为 0

---

## [M1.8] — 2026-08-11

### Codex 接管准备与仓库上下文固化

- 新增 `AGENTS.md` 仓库级 Agent 入口、冷启动协议与架构铁律
- 将 `CLAUDE.md` 扩展为 Claude / Codex / 其他代码 Agent 通用开发协议
- 同步 Settings、README、路线图与交接状态至 M1.8
- 核实封板 Tag `m1.7.2-m0-m1正式封板` 指向 `23d8ddb94a166d51fa7ba0d14620320b3e8d6b75`
- 生产业务逻辑变化为 0；M2 尚未开始

---

## [M1.7.2] — 2026-08-05

### M0—M1 最终文档收口与封板

**目标：** M0—M1 最后一个版本，只修正文档状态并建立封板流程，不新增功能、不修改业务逻辑、不进入 M2。

**主要变更：**
- 文档状态最终同步：docs/08、docs/09、README 全部更新至 M1.7.2
- 历史 Commit 和 CI 事实回填：M1.7 回填 `e5d1740`，M1.7.1 回填 `1dd20de` 及 CI Run #30991136311
- 新增"文档先于 Commit"规则：固化为 CLAUDE.md 硬规则，Commit 后禁止再回填文档
- 版本同步至 M1.7.2（Settings.version、README、docs/08、docs/09）
- 不修改生产业务逻辑（变化为 0）
- 不执行真实 LLM（调用次数为 0）

**固定封板 Tag：** `m1.7.2-m0-m1正式封板` — 该 Tag 必须指向本封板基线提交，远程 CI 通过后创建。

**Commit：** 该 Tag 必须指向本封板基线提交

---

## [M1.7.1] — 2026-08-05

### 最终状态收口与封板候选修复

**目标：** M1.7 终审发现 4 个小问题的收口修复，不新增功能、不进入 M2。

**修复内容：**
- 修正 docs/08 M1.6.6 详细章节状态冲突（进行中 → 已完成）
- 修正 docs/09 PydanticAI 错误描述（已从生产依赖移除，ADR-001 已被 ADR-005 替代）
- 删除恒真测试 `test_no_stale_tag_for_current_version`（仅 `assert True`）
- 加固 CI 工作区干净检查（git diff --check + git diff --exit-code + git status --porcelain）

**最终测试结果：**
- pytest：1119 passed（M1.7 的 1120 减去 1 个删除的恒真测试）
- Golden Cases：11 passed，1 skipped
- 安全扫描：PASS
- 错题本校验：PASS
- 架构门禁：PASS
- 真实 LLM 调用次数：0
- 生产业务逻辑变化：0
- 未创建 Tag

**Commit：** `1dd20de`

---

## [M1.7] — 2026-08-05

### MVP轻量化与通用CI固化

**目标：** M0—M1 正式封板前最后一次整理 — 测试收敛、CI通用化、文档轻量化、Smoke移出生产包。

**主要变更：**
- 测试收敛：删除4个旧集成测试文件（已被更强领域测试覆盖），版本化测试文件重命名为领域名称
- CI通用化：`.github/workflows/ci.yml`（PowerBIAgent Validation），动态版本一致性由pytest保护
- Smoke轻量化：删除4个阶段性Smoke，只保留一个人工验收入口（`scripts/manual_smoke/deepseek_chat_smoke.py`）
- 文档轻量化：归档M1.6审计文档、压缩docs/09和活跃CHANGELOG
- 版本同步至M1.7

**最终测试结果：**
- pytest：1120 passed
- Golden Cases：11 passed，1 skipped
- 真实 LLM 调用次数：0
- 生产依赖变化：0
- 生产业务逻辑变化：0
- 未创建 Tag

**Commit：** `e5d1740`

---

## [M1.6] — 2026-08-04 ~ 2026-08-05

### 架构收口与加固（M1.6.1—M1.6.6）

**目标：** 审计复验、架构定案、Harness收口、统一TurnPipeline、旧Agent清理、AI真实性加固、错题本治理、CI建立。

**关键架构决定：**
- ADR-005：确定性TurnPipeline与受控LLM调用架构（废弃PydanticAI）
- Memory单写入者：TurnPipeline为唯一事务入口
- ToolGateway为Power BI/Renderer唯一调用入口
- AST架构门禁替代grep检查

**最终验收（M1.6.6）：**
- pytest：1253 passed | Golden Cases：11 passed，1 skipped
- 安全扫描：PASS | 远程CI（Run #30983637121）：全部通过
- Commits：`0f6424f` → `208bca4` → `d6665bd` → `d99d243` → `d57e38c` → `4217b66` → `e850f14`/`cb2826e`/`762f4cf` → `084aa76`

---

## [M1.5] — 2026-08-03

### 全链路验收与M1封板

**Tag：** `m1-deepseek-pipeline-release` | **Commit：** `a926b5e`

**主要能力：**
- DeepSeek Chat全链路：Intent → QueryPlan → DAX → Mock QueryResult → Answer/ReportSpec → Memory
- TurnServiceProtocol通用协议 + Mock/DeepSeek双Service
- API模式切换：Mock/DeepSeek Health 200/503
- ChatResponse扩展 + Token/repair统计

**测试结果：** pytest 937 passed | Golden Cases 11/1 | 安全扫描 PASS

---

## [M1.4] — 2026-08-03

### 真实Answer与ReportSpec生成（含M1.4.1修复）

**主要能力：** DeepSeekAnswerService/ReportSpecService、Evidence强制绑定、KPI/Table/Chart严格验证、模板冲突拒绝

**测试结果：** pytest 936 passed | Golden Cases 11/1

---

## [M1.3] — 2026-08-03

### 真实QueryPlan与DAX生成（含M1.3.1修复、M1.3.2前端文档）

**主要能力：** DeepSeekQueryPlanService/DAXService、DAX只读安全验证器、QP真实验证、结构化回答契约

**测试结果：** pytest 706 passed | Golden Cases 11/1

---

## [M1.2] — 2026-08-03

### 真实意图识别

**Commit：** `53cf43e`

**主要能力：** DeepSeekIntentService、IntentContextSnapshot、意图严格化、集中式Prompt

**测试结果：** pytest 604 passed | Golden Cases 11/1

---

## [M1.1] — 2026-08-03

### DeepSeek Provider基础接入

**Commit：** `073a819`

**主要能力：** DeepSeekLLMProvider、10种异常类型、Provider Factory、真实连通测试

**测试结果：** pytest 506 passed | Golden Cases 11/1

---

## [M1.0 — M1.0.2] — 2026-07-31

### M0遗留收口、幂等并发、密钥安全

**Commits：** `9247322`、`c223d7b`、`5726959`

**主要能力：** 请求指纹与冲突检测、并发Owner/Waiter防重、Report快照结构化、密钥安全规则固化

**测试结果：** pytest 415 passed | Golden Cases 11/1

---

## [M0.4 — M0.4.1] — 2026-07-31

### 项目骨架与阶段收尾

**Tags：** `m0.4.1-foundation-release`、`m0.4-foundation-release`

**主要能力：** FastAPI最小骨架、API骨架真实性修复、请求级并发上下文收口

**测试结果：** pytest 285 passed | Golden Cases 11/1

---

## [M0.1 — M0.3] — 2026-07-31

### 仓库初始化、架构设计与验证闭环

**主要能力：** 项目文档基线、四层记忆系统、Power BI MCP设计（ADR-003）、ETCLOVG Harness（ADR-004）、ToolGateway、Golden Cases

---

*最后更新：2026-08-18 | M4.1 — SQLite 记忆与请求快照持久化*
