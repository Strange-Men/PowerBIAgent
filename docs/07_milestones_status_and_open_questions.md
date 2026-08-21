# 07 — 里程碑状态与待确认事项

> **状态：** M5.2 — 真实业务链路与前端逻辑收口已完成；M5.3 未开始
> 详细历史见 `CHANGELOG.md`、`docs/08_development_roadmap.md` 与 Git。

## 里程碑总览

| Milestone | 交付范围 | 状态 |
|---|---|---|
| M0—M1 | 项目基础、契约、Harness、FastAPI、DeepSeek、统一 TurnPipeline | ✅ 已封板 |
| M2 | Local MCP + Desktop、Semantic Grounding、Deterministic DAX、VerifiedFactSet | ✅ `m2.6.4-m0-m2-final-seal` 正式封板 |
| M3.0 | 报表架构、单一销售模板合同、M3 PBIX schema/Real baseline | ✅ commit/push/GPT remote audit PASS；已合入 main |
| M3.1 | 真实销售报表、固定 HTML、ReportArtifact、查看/下载 | ✅ 远程审计 PASS、已合入 main，CI success |
| M3.2 | 确定性 CSS 可视化、静态安全、Real 与视觉 hardened acceptance | ✅ 完成，无 Tag |
| M3.3 | 报表模板V2、信息架构去冗余、capability-aware section | ✅ 已完成 |
| **M3.4** | **自适应报表规划 + 可视化/布局策略（ADR-011）** | ✅ **已完成** |
| **M4.0** | **本地持久化架构与存储基础：SQLite/SQLAlchemy Async/Alembic/Repository ABC** | ✅ **已完成** |
| **M4.1** | **Memory/Snapshot SQLite 实现 + 并发提交 invariant** | ✅ **已完成** |
| **M4.1.1** | **会话创建竞态与数据库错误语义加固** | **✅ 已完成** |
| **M4.1.2** | **SQLite Transaction Failure & Error Semantics Hardening** | **✅ 已完成** |
| **M4.1.3** | **SQLite Lock Transaction Exit Final Hardening** | **✅ 已完成** |
| **M4.2** | **Conversation/Report recovery（会话与报表元数据恢复）** | **✅ 已完成** |
| **M4.2.1** | **Report metadata authority & linkage hardening** | **✅ 已完成** |
| **M4.2.2** | **路径与元数据一致性最终加固** | **✅ 已完成** |
| **M4.2.3** | **持久化资源身份与元数据权威最终收口** | **✅ FINAL PASS** |
| **M4.3** | **Namespace-first recent/history/search/archive/delete API** | **✅ 已完成** |
| **M4.4** | **Restart/crash acceptance + M4 backend final closure** | **✅ M4 FINAL PASS** |
| **M4.4.1** | **Committed Memory corruption fail-closed + README/document closure** | **✅ FINAL PASS** |
| **M4.4.2** | **M0–M4 truth / persistence boundary final closure** | **✅ FINAL PASS** |
| **M5.0** | **前端设计与契约固化（文档校准、页面结构、交互边界、动态回答原则、UI↔后端能力映射）** | **✅ 已完成** |
| **M5.1** | **React + Vite 前端实现与核心联调** | **✅ 已完成** |
| **M5.2** | **真实业务链路与前端逻辑收口** | **✅ 已完成** |
| M5.3 | 视觉与交互最终收口 | ⬜ 待开始 |

## M3 合并与 CI truth

- M3.0 commit：`e4b5c6c6a759cdf22c74c4d87902482563e27cad`。
- GPT 远程架构审计：PASS。
- `main` 从 M2 seal `70748daabfa5d3dd250f17fe22f0c892c7a30b74` 纯 fast-forward 到 M3.0 commit，无 merge commit/rebase/force push。
- main push 触发 `PowerBIAgent Validation` run `31986207118`，head SHA 与 M3.0 commit 一致，结论 `success`。
- M3.1 commit：`fa4cc0c97a10bcc0867c414dc3fa2d7fa9b35e57`；远程审计后从 M3.0 纯 fast-forward 合入 main，main push run `31989328261` 对应同一 SHA，结论 `success`；本地与远程开发分支随后删除。
- GitHub CI、本地 pytest/Golden/gates、Real Power BI smoke 与静态视觉检查是不同证据，必须分别描述。

## 当前能力状态

| 能力 | 状态 |
|---|---|
| TurnPipeline / ToolGateway / PowerBIAdapter 单一控制面 | ✅ M2 封板骨架保持不变 |
| M3 production template | ✅ 仅 `sales_report`；legacy/unknown unavailable |
| ReportDataPlan | ✅ 由 capability 解析出的查询子集（M3.4），不读 LLM draft |
| ReportPlan / Capability Engine | ✅ 9 个 registry-owned sections；schema-aware 门控（contract 声明 + runtime 对象/类型 + 已验证非空事实）；缺能力 UNAVAILABLE，不 Mock |
| Report Intent weak signal | ✅ LLM 只输出 registry-owned section ID；确定性匹配器为地板；单独计数 llm_report_intent_call_count |
| SalesReportData / ReportSpec | ✅ N 组 QueryResult / VerifiedFactSet 确定性组装；ChartSpec 结构化扩展（visual_type/business_role/series/layout_hint） |
| Visualization / Layout / Theme Policy | ✅ KPI Card / Line / Donut≤8 / Column / HBar；KPI 行 → 全宽趋势 → 2 列对比/排行对；固定调色板与响应式 |
| SalesReportRenderer (design system) | ✅ 固定 UTF-8 static HTML；inline SVG line/donut、CSS column/hbar；无同源表格重复；无 JS/CDN/外部资源/自由 HTML |
| ReportArtifact | ✅ filesystem HTML authority、required metadata contract、immutable report_id、原子本地保存 |
| Resource API | ✅ view/download；unknown/path traversal 拒绝 |
| Idempotency / Memory | ✅ replay 复用 report_id；render/store failure 不成功提交 Memory |
| Persistent sessions / React | ✅ SQLite session query lifecycle + React recent/search/history/reports adapters 已完成 |
| Persistence Architecture (M4.0) | ✅ ADR-012、SQLite/SQLAlchemy Async/Alembic、5 表 schema、migration 基线、Repository ABC |
| Memory / Snapshot SQLite 实现 (M4.1) | ✅ SQLiteMemoryRepository + SQLiteSnapshotRepository production wiring、DB 级 partial unique index 并发安全、strict concurrent commit tests |
| SQLite 错误语义硬化 (M4.1.1) | ✅ conversation root `INSERT OR IGNORE` 原子 upsert、`PersistenceRepositoryError`、locked/version_index 分类 helper |
| SQLite 事务失败硬化 (M4.1.2) | ✅ failed transaction fresh-session conflict resolution、real OperationalError injection tests、infrastructure failure 与 business version conflict 严格分离 |
| SQLite 锁事务退出最终硬化 (M4.1.3) | ✅ locked failure 必须退出原 transaction 再 fresh-session resolution、真实 SQLite lock integration test、M4.1 series final hardening |
| Conversation/Report recovery | ✅ M4.2 / M4.2.1 |
| Report persistence final invariants | ✅ M4.2.3；row/payload 缺失或冲突 fail closed；完整 metadata 相同才幂等；history namespace=`(source_mode, conversation_id)` |
| Search/History API | ✅ M4.3；structured history、bounded cursor pagination、archive/delete |
| Restart / Crash Acceptance | ✅ M4.4；fresh engine/service recovery、terminal vs incomplete semantics、filesystem report replay、durable delete intent/retry |
| Committed filter corruption boundary | ✅ M4.4.1；deserialize + StateTransition 双边界 fail closed，不降级为空 filter，不产生 LLM/DAX/Power BI/新 commit |
| Truth / Persistence final closure | ✅ M4.4.2；完整 WorkMemory payload、mandatory runtime namespace、row/payload integrity、Snapshot replay 与非 legacy time corruption fail closed |

## `sales_report` 能力目录（M3.4）

模板 = 固定设计规则 + 允许能力目录（ADR-011）；报表针对各 PBIX 全量数据，不接受动态月份、Category filter、比较、用户自由 ReportDataPlan 或任意 DAX。最终 section 由用户需求 ∩ runtime schema 能力 ∩ catalog 决定。

| Requirement | Measure | Dimension（表） | Sort / TopN |
|---|---|---|---|
| `total_sales` | Total Sales | — | — |
| `total_quantity` | Total Quantity | — | — |
| `total_orders` | Total Orders | — | — |
| `average_order_value` | Average Order Value | — | — |
| `monthly_sales` | Total Sales | YearMonth（Date，display asc） | — |
| `sales_by_category` | Total Sales | Category（Sales） | — |
| `sales_by_region` | Total Sales | Region（Sales） | — |
| `top_products` | Total Sales | Product（Sales） | desc / 5 |
| `top_customers` | Total Sales | Customer（Sales） | desc / 5 |

TopN 对外只使用 `result_position` / QueryResult order，不声明严格 business rank；boundary ties 可使结果超过 5 行。

## M3.2 hardened acceptance

- 未新增 template、query、DAX、filter、business fact、chart type、resource API、persistence 或 frontend；只把既有两组 `ChartSpec` / table rows 以固定 CSS 横条和同源表格呈现。
- 横条宽度由已验证行值在组内按绝对最大值归一化，固定半入舍入到两位小数；可视数值仍显示原始已验证值。
- 窄屏使用固定 Flex 换行保持 label/value/bar 对齐；桌面与 430px 静态渲染均经视觉检查 PASS。
- HTML 保存前拒绝 active script、external URL 及 `link` / `iframe` / `object` / `embed` / `@import` / `url()` / `src=`。
- DeepSeek prompt 明确只保留弱语言信号；报表 template、四查询、KPI、chart/table 事实、HTML/CSS、布局、保存与资源引用 authority 均为 0。

## M3.4 Adaptive Report Planning changes

- ADR-011 supersede ADR-010 的"一个 template 永久绑定一个 model fingerprint + 固定四 queries"限制；固定事实安全边界继续有效；contract version 升至 2.0
- capability.py 重构为 schema-aware capability engine：9 个 registry-owned sections，按 contract 声明 + runtime schema 对象/类型 + 已验证非空事实三层门控
- 新增 ReportPlanner / ReportPlan（requested/resolved/unavailable、去重 query requirements、provenance）；请求子集才查询；零可解析 section fail closed
- 新增受控 Report Intent weak signal（LLM 只输出 registry ID；未知 ID 丢弃；确定性匹配器为地板；只看…忽略增量；单独计数）
- 新增 VisualizationPolicy / LayoutPolicy / ThemePolicy；`SalesReportRenderer` 渲染 KPI cards、inline SVG line/donut、CSS column/hbar；同一业务事实不重复展示
- 时间趋势复用 M2 密封链（grouped query → VerifiedFactSet），Renderer 不聚合；已验证时间点仅做确定性显示排序
- 最小通用扩展：`CanonicalQueryPlan.dimension_tables` / `dimension_order`、ChartSpec 结构化字段；Simple 模型行为与 M3 基线一致
- 双模型 Real acceptance：Simple 4 sections/4 queries；Rich 9 sections/9 queries、4 种 visual；事实类 LLM counters 全 0

## M4.0—M4.4.2 Persistence changes

- **M4.0**：新增 ADR-012（本地持久化架构）：SQLite + SQLAlchemy Async + aiosqlite + Alembic；`backend/app/persistence/` 包（database.py / models.py / serialization.py）；5 表 schema + UNIQUE + FK；Alembic 迁移基线；Settings 扩展（默认 memory）；Repository ABC；1517 tests。
- **M4.1**：SQLiteMemoryRepository + SQLiteSnapshotRepository production wiring（`main.py` → `MockTurnService`/`DeepSeekTurnService`）；DB 级 partial unique index `ix_work_memories_committed_version`（`WHERE state_status = 'committed'`）保证同 (runtime_mode, conversation_id, memory_version) 最多一个 COMMITTED 行；`commit()` 内 `IntegrityError`/`OperationalError` → `MemoryVersionConflictError`；strict concurrent commit tests（exactly-one-success + 8 轮多轮验证）；corrective migration `ab8d7df39a02`。1559 tests。
- **M4.1.1**：conversation root `INSERT OR IGNORE` 原子 upsert、`PersistenceRepositoryError` 异常类、`_is_sqlite_locked`/`_is_version_index_conflict` 分类 helper、failed transaction 不污染后续 ops。
- **M4.1.2**：locked/busy OperationalError 退出原 transaction → fresh session bounded reread（`_resolve_locked_commit_failure` helper）；non-lock OperationalError → `PersistenceRepositoryError`；通过 `session.execute` 拦截真实注入 OperationalError 测试（non-lock、locked+version advanced、locked+unchanged、fresh session proof、failed tx recovery、no half-committed memory）。
- **M4.1.3**：locked failure 必须在原 transaction 退出（rollback）后再 fresh-session resolution；`commit()` 中捕获 locked 后只保存 context → `session.begin()` exit 后调用 resolver；`create_engine` 新增 `busy_timeout` 参数（测试 100ms，production 5000ms）；真实 2-engine SQLite lock integration test（Writer A hold lock → B commit hit lock → tx exit → fresh reread）、instrumented session-exit 顺序证明（`write_tx_enter → locked → write_tx_exit → fresh_session`）。M4.1 series final hardening。
- **M4.2.3**：modern ReportArtifact payload 的 7 个 authority 字段 required；linkage nullable 但 DB 有值时 payload 不得缺失；row/payload 缺失或冲突统一 fail closed。`report_id` immutable，SQLite/InMemory 仅允许完整 metadata 相同的幂等 no-op；report history namespace 固定为 `(source_mode, conversation_id)`。M4.2 series FINAL PASS。
- **M4.3**：新增 SQLite `ConversationHistoryRepository` + application query service + FastAPI endpoints。Conversation 方法强制 `runtime_mode`，report history 强制 `source_mode`；recent=`updated_at DESC, conversation_id ASC`，terminal snapshot transaction touch root；history authority=result snapshot + optional committed memory + strict report metadata，不提供 transcript；search 仅查 committed `analysis_goal` 与 snapshot answer/clarification/unsupported，不引入 FTS5；archive 逻辑隐藏，delete 物理级联同 namespace DB rows/HTML。Migration `f4c3a2b1907d` 增加 `archived_at` 与复合查询索引。
- **M4.4**：使用临时真实 SQLite/report filesystem 与 dispose → fresh engine/session/repository/service 验证 restart。terminal Snapshot 是唯一 request replay authority；Memory-without-Snapshot 是 incomplete crash witness 并 fail closed。持久化 report snapshot 不保存 HTML，重放必须从 filesystem 加载并验证 metadata/hash/linkage/namespace。delete transaction 新增 durable intent，保存精确 report IDs/counts；HTML cleanup 成功后 finalize，失败或 crash 可由新实例重试，intent 期间拒绝同 namespace 复活。Migration `c8d4e6f2a109`；fresh 与 M4.3 → head PASS；backend `1681 passed, 1 skipped`。M4 FINAL PASS，M5 NOT STARTED。
- **M4.4.1**：committed canonical filter 在 domain deserialize 时逐项验证；StateTransition 遇到 malformed filter 抛出稳定 corruption error，不再 `continue`。真实临时 SQLite restart regression 参数化覆盖 Mock/Real，同 namespace 不生成 LLM/DAX/Power BI 调用或新 memory version，另一 namespace 合法数据继续恢复。README 重构为长期 Landing Page，状态文档同步；无 migration。M4.4.1 FINAL PASS，M5 NOT STARTED。
- **M4.4.2**：移除 committed WorkMemory payload 缺失时的 partial column fallback；modern payload 必须完整且通过 domain validation，并与 row integrity fields 一致。Memory conversation methods 的 runtime namespace 在 ABC/InMemory/SQLite 与 production callers 中 mandatory；修复 InMemory exact-ID cross-mode overwrite。terminal Snapshot row/payload 冲突与非 legacy committed time corruption 同样 fail closed。Targeted/adjacent `607 passed`；backend `1700 passed, 1 skipped`；Golden/gates/fresh Alembic PASS；无 migration。M4.4.2 FINAL PASS，M5 NOT STARTED。

## M3.3 Report Template V2 changes

- 重构 sales_report 信息架构：每 section 回答一个独立业务问题，同一业务数据默认只展示一次；移除 Category bars 下方重复明细表、Top Product bars 下方重复明细表
- 新增 `backend/app/report/capability.py`：SectionCapability 概念，根据 runtime schema + TemplateContract + VerifiedFactSet 确定性判断 section availability；SALES_KPI、CATEGORY_BREAKDOWN、TOP_PRODUCTS 三个可渲染 section；TIME_TREND / REGION_BREAKDOWN / CUSTOMER_BREAKDOWN 为纯 extension point
- `FixedSalesReportRenderer` 改为 capability-aware：缺失 section 不输出 placeholder、不伪造 chart，section unavailable 时完全不出 HTML
- 多语义模型防伪：Model A 当前 schema 所有 section 正常；Model B 多 Date/Region/Customer 字段不自动生成 section；Model C 缺 Category/Product 时 contract validation fail closed
- 未新增业务查询、DAX、filter、template、LLM authority 或事实来源；四查询集合保持不变，PBIX 不变
- 新增 regression tests：no duplicate visual、capability evidence gate、extension point 防自动激活

## 待确认事项

| 事项 | 决策时点 |
|---|---|
| M5.1 状态管理 | ✅ React hooks，未引入全局状态框架 |
| 统一前端 Envelope | ✅ M5.1 不新增；typed adapter 直接消费现有 ChatResponse/History schema |
| 前端结构化表格/图表数据 | M5.2 审计确认 Chat/History 不暴露 QueryResult rows/ChartSpec，未新增高风险 adapter、不从 answer/audit 反解析；明确 defer 至 M5.3 前的契约补充 |
| Remote MCP 管理员与授权条件 | 重新批准 Remote 后 |

## 当前真实风险

- Simple M3 PBIX runtime `OrderDate` 为 `Int64`；Simple 模型无时间趋势能力（TIME_TREND UNAVAILABLE），不得伪装为 DateTime。Rich PBIX `OrderDate` 为 `DateTime` 且含 Date 表，趋势能力真实解析。
- Capability 目录随 runtime schema 变化；schema 变更需按能力目录重新人工 smoke（不再依赖单一 fingerprint gate）。
- Local Modeling MCP 仍为 Preview；官方包、Desktop 或协议变化后需重新人工 smoke。
- Report HTML 仍以 filesystem 为 authority；Snapshot 只存 replay metadata。M4.4 delete intent 只记录同 `source_mode` linkage 的精确 report_id，不跨 namespace cascade；本轮保证经测试的应用级 retry/recovery，不宣称 SQLite 可与 filesystem 原子提交或覆盖硬件掉电。
- Committed Memory 的 modern payload 必须完整且与 row integrity fields 一致；缺失、空、malformed/incomplete/domain-invalid payload 均 fail closed，不得从 partial columns 重建或通过清空/default 扩大语义。合法 legacy time string compatibility 保持不变。
- PBIX、真实输出、HTML 与 `local_state/` 永不提交。

## Tag 与基线

| 项目 | 值 |
|---|---|
| M0—M2 Final Seal | `m2.6.4-m0-m2-final-seal` → `70748da` |
| M3.0 main | `e4b5c6c`；CI run `31986207118` success |
| M3.1 main | `fa4cc0c`；CI run `31989328261` success；开发分支已删除 |
| **M0—M3 Final Seal** | **`m3.4-m0-m3-final-seal` → `ff8aca23`** |

---

*最后更新：2026-08-21 | M5.2 — 真实业务链路与前端逻辑收口完成*
