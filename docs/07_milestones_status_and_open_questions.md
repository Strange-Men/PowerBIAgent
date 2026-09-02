# 07 — 里程碑状态与待确认事项

> **状态：** M5.8.4 — 跨语言与通用模型理解优化（COMPLETE；`a975310` exact-SHA CI completed/success）
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
| **M5.2.1** | **模型能力边界与真实模式说明收口** | **✅ 已完成** |
| **M5.3** | **结构化结果、历史/标题/资源管理与视觉交互最终收口** | **✅ 已完成** |
| **M5.3.1** | **Local Desktop 单实例安全 + presentation verified-field projection** | **✅ 已完成** |
| **M5.3.2** | **多 PBIX 选择、opaque instance binding 与 MCP beta 稳定性** | **✅ 已完成** |
| **M5.3.3** | **多轮继承语义、conversation/report 生命周期与 Artifact Governance** | **✅ 已完成** |
| **M5.4** | **conversation-scoped state、异会话并发、用户卡片/资源管理、report tombstone/rename** | **✅ 已完成** |
| **M5.4.1** | **Settings Hub、全量 conversation/report 分页、准确全选语义与 automation artifact cleanup** | **✅ 已完成** |
| **M5.4.2** | **M5 重建基线、旧实验线审计保留、分阶段路线与 Generalization Gate** | **✅ COMPLETE** |
| **M5.5** | **Semantic correctness：Grounding/member/multi-turn/TopN/time/capability** | **✅ COMPLETE** |
| **M5.6** | **Presentation、Localization 与 Resource UX truth** | **✅ COMPLETE** |
| **M5.7** | **简易报表视觉 + Report Template Required + Real Browser 人工视觉 Gate** | **✅ COMPLETE** |
| **M5.7.1** | **统一语义可靠性、回归防火墙与高强度问答验收** | **✅ COMPLETE** |
| **M5.7.2** | **Report Template Gate 前移、Template/Renderer Registry、前端模板选择 UX、简易模板视觉与信息架构最终修复** | **✅ COMPLETE** |
| **M5.8** | **多 LLM Provider 抽象 + DeepSeek/Kimi 最小双模型** | **✅ COMPLETE** |
| **M5.8.1** | **前置性能加速与本地 MCP 会话复用** | **✅ COMPLETE** |
| **M5.8.2** | **通用自然语言路由与查询形态收口** | **✅ COMPLETE** |
| **M5.8.3** | **MCP-driven ModelSemanticContext 与任意 PBIX 通用语义适配** | **COMPLETE（b86662e / CI success）** |
| **M5.8.4** | **现有语义链跨语言与通用模型理解优化** | **COMPLETE；`a975310` exact-SHA CI completed/success** |
| **M5.9** | **完整 MCP performance/resilience、并发压力与故障恢复** | **⏳ NOT STARTED** |
| **M5.10** | **固定专业销售报表模板与两模板选择** | **⏳ NOT STARTED** |

## M5 重建决策与历史状态

- 新开发分支为 `m5/rebuild`，唯一基线是 M5.4.1 commit `cab40b076f054a3ebdab0bf6d2b0354f4b2d49db`。
- 旧实验线 `m5/frontend`、`a197db3ecfe8959f3f8bb79e18d7ee02834fedd3`（原 M5.5）、`6d1620a7a7aa04e65692371436d90756fdf5bcc8`（原 M5.5.1）永久保留为研究、失败经验与审计记录。
- 不删除、不重写、不 revert、不整体 cherry-pick 旧实验线。可以参考单项思想，但必须在新阶段重新实现并重新完成 Focused Real、Cross-domain、Full gates 与用户人工验收。
- M5.4.2 不修改生产业务逻辑；M5.4.1 及以前能力全部保留。完整长期合同见 `docs/specs/13_m5_generalization_and_acceptance_contract.md`。

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
| M5.3.3 lifecycle | ✅ fresh/follow-up/replace、unsupported preflight、archive/restore、独立 report delete、A/B stale-response 防护与 Artifact Governance |
| Idempotency / Memory | ✅ replay 复用 report_id；render/store failure 不成功提交 Memory |
| Persistent sessions / React | ✅ SQLite session query lifecycle + React recent/search/history/reports adapters 已完成 |
| M5.3 presentation contract | ✅ QueryResult/VerifiedFactSet 单一 dataset + 动态 text/metric/table/bar/line/report 引用已实现并通过 Rich PBIX Real 验收 |
| M5.3.1 Desktop/presentation hardening | ✅ 多 Desktop 在 Connect 前 fail closed；额外未验证 QueryResult 字段不进入 presentation |
| M5.3.2 Local MCP multi-model hardening | ✅ 多 PBIX safe catalog、逐 session opaque 精确绑定、只读 capability probe、stale/truncation fail closed |
| Presentation transcript/title | ✅ Snapshot 保存 UI-only `user_message`/`presentation`；conversation title 自动生成、可重命名；不进入 Memory/factual authority |
| Conversation/report management | ✅ 重命名、归档与现有 namespace DELETE；报表按所属 conversation 管理并复用 durable delete intent |
| M5.4 concurrent sessions | ✅ `conversation_id → session`、client UUID pending row、异 conversation 并发/同 conversation 串行 |
| M5.4 resource manager | ✅ 用户卡片、最多 20 项 bounded bulk orchestration、partial failure UI |
| M5.4 report presentation lifecycle | ✅ deleted tombstone 与不改 hash/HTML/ReportSpec 的 `display_title` |
| M5.4.1 full resource management contract | ✅ Settings 独立分页全部 active/archived conversation/report；Recent 不再作为完整历史数据源 |
| M5.4.1 artifact ownership contract | ✅ automation-owned 资源显式登记、finally cleanup、零残留 Gate；未知 ownership 用户资源保留 |
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
| 统一前端 Envelope | ✅ 不增加跨 authority 的通用事件协议；M5.3 只在 ChatResponse/History 中增加 typed `presentation` 展示层 |
| 前端结构化表格/图表数据 | ✅ M5.3 从 QueryResult + VerifiedFactSet 确定性投影单一 dataset；blocks 只引用字段和 row，不从 answer/audit 反解析 |
| Remote MCP 管理员与授权条件 | 重新批准 Remote 后 |

## M5.4 不可退化契约

- 新 conversation 首条消息发送后必须立即出现于 Sidebar；前端 UUID 直接作为现有 Chat `conversation_id`。
- 不同 conversation 可并发；同 conversation 串行。loading/error/result 不跨 conversation，后台 chat 不因导航取消。
- 用户卡片承载设置/已归档/资源管理；Sidebar 最近区可折叠、独立滚动、不无限加载。
- archive ≠ delete；批量操作只协调单资源 API、最多 20 项，部分失败保留。
- report delete 保留 transcript tombstone；rename 只修改 presentation `display_title`。LLM 无 rename/delete 权限。
- M5.5 语言、中文字段、单指标展示、HTML 视觉和性能不在本轮开发。

## M5.4.1 不可退化契约

- 用户卡片只进入统一 Settings Hub；左导航为常规、对话管理、报表管理、已归档、数据模型、关于。
- Sidebar Recent 保持 bounded/轻量；Settings 对话与报表管理必须独立 cursor pagination，并显示 total/loaded/selected/has-more。active 与 archived 都必须可访问完整历史。
- “全选当前已加载”只选已加载项；不得把第一页、当前 DOM 或 recent subset 表述为全部匹配资源。完整历史至少必须可持续加载并多选任意项。
- 浏览与选择不受 20 项限制；一次确认的大集合由前端按最多 20 项一组调用正式单资源 API，partial failure 精确归属资源，不新增 `DELETE ALL`。
- 所有 Codex/pytest/browser/Real/MCP/report 自动化资源必须具有 explicit test ownership；`finally` cleanup 后验证 conversation/report metadata/HTML/SQLite namespace/delete intent residual=0，否则 Gate FAIL。
- 历史清理只处理有 ownership/known namespace/fixture/linkage 证据的 automation-owned 资源；无法确认的资源保留。M5.5 继续 Deferred。

## M5.5—M5.10 隔离边界

- **M5.5** 只处理 Semantic correctness；explicit unresolved member/filter 必须 clarification/no-match 且 ZERO DAX。禁止 Localization、Report Visual、MCP 性能优化与 Resource UI 大改。
- **M5.6** 只处理 canonical/display separation、Localization、格式化、Answer/Table/Chart 信息密度，以及 Settings/Recent/failed resource/toolbar/menu truth。conversation/report 必须共用 Portal/floating layer 和 viewport-aware above/below positioning；Settings 必须有 nested scroll contract 与 sticky/scrollable action toolbar。禁止改变 Grounding、DAX 或 MCP authority。
- **M5.7** 已完成现有 `sales_report.html` 的简易模板 information architecture、responsive、plot geometry、axis/tick、accessibility、可读性，以及 `Report Template Required` Gate。missing/invalid/stale template 均为 ZERO ReportData/ReportSpec/Renderer/artifact；42 组 visual matrix、Rich PBIX Real Browser/manual 与 automation-owned residual=0 通过。正式视觉 Gate 是普通用户能读懂，而非仅 SVG 不越界。
- **M5.7.1** 已完成 Intent、Object/Member/Temporal Grounding、StateTransition、multi-turn、ranking/capability 与永久 Semantic Compatibility Gate。日期角色来自显式用户角色、model-scoped metadata 或可证明的 runtime relationship/default role；无唯一证据才 clarification。answer leakage scanner 与 frontend/provider authority 检查均通过，未修改报表视觉/Registry、多模型或 MCP 性能。
- **M5.7.2** 已完成 Report Template Gate 前移、Template/Renderer Registry、简易模板视觉与信息架构最终修复。
- **M5.8** 已完成并冻结 `OpenAICompatibleLLMProvider`、`LLMModelProfile`、DeepSeek + Kimi-K2.6、request/conversation-scoped model selection 与同一 authority/regression contract。
- **M5.8.1** 已完成安全 profiling、Local MCP application-owned session reuse、非事实 metadata/member 短 TTL bounded cache、singleflight 与最小 bounded concurrency；未引入 Redis，未缓存事实/答案/DAX/QueryPlan。
- **M5.8.2** 已完成 Question Router、八类 Query Shape、shape-specific required slots、minimal clarification、安全 calculator/help/system-info、dimension-only/Top1/member-set/bounded trend 与跨域语义防火墙；非业务 turn ZERO schema/member/DAX/semantic Memory mutation。
- **M5.8.3** 只处理 MCP-driven ModelSemanticContext 与任意 PBIX 通用语义适配，Real 验收已通过，受控 temp cleanup 已自动化；正式 COMPLETE 以 fresh local/residual 与对应提交 CI success 为条件。
- **M5.9** 继续处理完整 queue/backpressure、20/50/100 concurrency、restart/fault matrix 与 soak；不得降低 factual validation 或修改 Semantic/DAX/VerifiedFactSet authority。
- **M5.8.4** 已完成现有语义链的跨语言绑定、runtime 成员验证、KEEP/REPLACE 与 Report/Data 状态收口；完整 A–E 复核、失败样本、最终门禁与 CI 条件见 [专项计划](milestones/m5/m5_8_4_cross_language_grounding_plan.md)。没有新建第二套模型/Planner/Catalog。
- **M5.10** 必须晚于 M5.9，只增加固定专业销售报表模板和显式两模板选择。“简易模板”是 M5.7 优化后的现有 `sales_report.html`；“销售模板”使用确定性专业版式。两者都只消费 VerifiedFactSet/ReportData/ReportSpec，不允许 LLM 生成 HTML/CSS/SVG、查询或事实。只有 M5.10 全部门禁完成后才允许声明 M5 FINAL。
- 每个 milestone 禁止同时大规模修改 Semantic、MCP、Presentation、Report、Resource lifecycle 多个域。

### M5.6 执行合同与 Layout Gate（COMPLETE）

- Localization binding 至少包含 model key、runtime object identity/type、canonical/display name、locale、source 与 schema identity；metadata/glossary/registry/bounded translation/fallback 按固定优先级解析，unknown runtime object 不得登记或翻译。
- presentation formatter 只生成显示值，覆盖 integer、decimal、percentage、currency/general amount、date、month、null；canonical value 不变。scalar 只显示自然语言，grouped/trend 的 Answer 只总结 verified insight，table/chart 承担完整细节。
- Settings/Recent report 共用正式 resource query；Recent conversation 固定 `updated_at DESC, created_at DESC, stable_id DESC`。failed conversation 持久化后必须支持 rename/archive/restore/delete，且 failed turn 不提交 Memory。
- conversation/report 共用 Portal-based floating menu；Settings 采用 fixed shell、独立 content/list scroll 与 sticky/scrollable toolbar。不得以 title、“测试”或用户名推断资源状态。

- first/middle/last row；scroll top/middle/bottom；100%/125% zoom；768/1080/1440 viewport height。
- Sidebar scroll 与 Settings nested scroll 分别验证。
- destructive action 始终可访问；floating menu 不受 scroll container、scrollbar 或 stacking context 裁切。

## 当前真实风险

- M5.5 的 explicit member、runtime alias、TopN、multi-turn slot 与 temporal semantic 风险已关闭；M5.6 的 canonical time 展示与信息密度 Gate 已通过。
- Settings/Recent truth、newest-first、failed conversation 管理、toolbar 可达性与 floating menu overflow 已在 M5.6 关闭。
- 报表“未裁切”仍不等于可读；时间轴、跨年标签、plot area、空白与 donut/legend 密度必须在 M5.7 经 Real Browser 人工视觉验收。
- M5.8.1 已消除每次 operation 重启 Local MCP 的主要成本，并完成短 TTL/stale/cold-warm 小批验证；完整 queue fairness/backpressure、20/50/100 concurrency、fault matrix 与 long soak 仍必须在 M5.9 独立验证。

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
| M5.4.1 rebuild baseline | `cab40b076f054a3ebdab0bf6d2b0354f4b2d49db` |
| 原 M5.5 / M5.5.1 实验线 | `m5/frontend`：`a197db3` → `6d1620a`（保留，不是新基线） |

---

### M5.4 fresh evidence

- Rich PBIX A/B/C 在同一浏览器中并发执行，Sidebar provisional row 立即可见；active C/B 不显示其他会话 loading，三个结果只写回所属 session，完成后不自动跳窗。
- 用户卡片设置面板、归档/恢复、两次 report generation、rename、delete 后 history tombstone 已通过 Real Browser Acceptance；本轮 9 个测试 conversation 与关联 report 已经正式 API 精确清理。
- Backend full `1790 passed, 1 skipped`；frontend typecheck/lint/build PASS，Vitest `61 passed`；Golden `11 passed, 1 manual-real skipped`；Architecture `117`、Repository Safety `290`、Error Ledger `25`、Documentation Governance、Artifact Governance 与 `git diff --check` PASS。
- 新增 Alembic revision `a4f6b8c2d190`。LLM 无 conversation/report rename/delete tool；M0–M5 factual authority 不变；M5.5 未开始。

### M5.4.1 fresh evidence

- Real Browser：25 个 owned conversations 首屏 20/25、加载到 25/25；Sidebar 保持 12；25 项单次确认按 20+5 bounded waves 完成 archive/restore。
- 10 个 owned reports 独立分页可见，rename/archive/restore/delete 与最后标题 tombstone 通过；restart 后状态正确。
- teardown 后 conversation/report/HTML/SQLite/delete-intent exact residual=0；无法确认 ownership 的资源未删除。
- Backend `1797 passed, 1 skipped`；Vitest `69 passed` 且 typecheck/lint/build PASS；Golden `11 passed, 1 manual-real skipped`；Architecture `118`、Repository Safety `295`、Error Ledger `27`、Documentation/Artifact Governance 与 `git diff --check` PASS。

### M5.4.2 fresh evidence

- `m5/rebuild` 从 `cab40b076f054a3ebdab0bf6d2b0354f4b2d49db` 创建；原 `m5/frontend` 仍指向 `6d1620a`，历史未重写。
- Documentation Governance、Repository Safety（296 files）、Error Ledger（30 entries）、Artifact Governance 与 `git diff --check` PASS。
- 仅版本元数据与文档/治理文件变化；无生产业务逻辑、测试、schema 或 migration 变化，未开始新版 M5.5。

### M5.5 fresh evidence

- explicit unresolved member 已由最接近生产入口的回归证明 clarification/no-match、ZERO DAX/QueryResult/Memory commit；`火星区` 不再降级为全国结果，`华南/华南区/南区` 仅在 runtime member authority 支持时 canonicalize 为 `South`。
- Real Rich PBIX 四轮 `2025年5月销售额 → 那南区呢 → 换成去年 → 前三个产品呢` 完成 slot-level KEEP/REPLACE；Top3/descending、time filter/grouping 与 prediction/delete capability boundary 正确。
- Sales、Education、Inventory、未知 opaque holdout 与 display/table rename、相似字段、glossary alias 删除、member change、unknown/ambiguous member mutation 全部通过 deterministic oracle；生产 semantic 代码未引入 sales-specific field/member hardcode。
- Backend full `1823 passed, 1 skipped`；frontend `69 passed` 且 typecheck/lint/build PASS；Golden `11 passed, 1 manual-real skipped`；Architecture `118`、Repository Safety `296`、Error Ledger `32`、Documentation/Artifact Governance、compileall 与 Local MCP readonly smoke PASS。
- Real API 与 Browser 人工验收通过；unknown member 可见 clarification，South 与同会话 Top3 正确完成，automation-owned acceptance residual=0。M5.6 与 M5.7 已完成；M5.8—M5.10 未开始。
- M5.7.1 Semantic Compatibility Gate `302 passed`；backend full `1901 passed, 1 skipped`；frontend `80 passed` 且 build PASS；Golden `11 passed, 1 manual-real skipped`；Sales/Education/Inventory/unknown holdout、schema mutation 与 Rich PBIX Real/manual 均通过，automation-owned DB/artifact residual=0。
- M5.7.2 将 Template Gate 固定在 Intent 后并证明 missing/unknown/stale 时 ZERO schema/DAX/report downstream；建立 Template/Renderer Registry、后端只读模板目录与前端显式选择。简易模板完成 4 KPI、趋势、区域/品类、Top 产品、关键明细、footer 及 Y 轴/grid/15 月/小屏跨年 tick 收口；Semantic Compatibility `304 passed`、backend `1918 passed, 1 skipped`、frontend `83 passed`、Golden `11 passed, 1 manual-real skipped`，automation-owned residual=0。M5.8—M5.10 未开始。

### M5.8 完成合同（COMPLETE）

- `LLMProvider` 继续作为上层唯一协议；DeepSeek 与 Kimi 共享一个 `OpenAICompatibleLLMProvider`，差异仅来自不可变 `LLMModelProfile` 与 Secret-bearing runtime configuration，禁止复制 Kimi Turn/Intent/QueryPlan/Answer Service。
- Provider Registry 只允许 `profile_key → provider/profile` 显式解析，不提供用于用户切换的全局 mutable default。每个 turn 开始时解析并快照 profile，Intent/QueryPlan/Answer 等同轮调用只能使用该快照。
- 模型选择属于 request/conversation-scoped presentation/runtime choice，不是 factual/semantic state；切换 profile 保留 Structured Memory 与 canonical slots，但 provider opaque session state 不得进入 authoritative Memory。
- `configuration/authentication/rate_limit/timeout/connection/request/service/response_validation` 使用 provider-independent taxonomy；trace 只记录 public profile/model、task、usage、error class，禁止 Key、Authorization、Secret query 与原始敏感响应。
- DeepSeek/Kimi 必须共享永久 Semantic Compatibility Gate；malformed/invalid structured output 最终受控失败，ZERO incorrect Memory/fact commit；禁止 silent fallback、auto-routing、ensemble。
- Rich PBIX 双模型同题集的 canonical plan 与规范化 QueryResult 一致；unknown/unsupported fail closed、`sales_report` 固定链、并发 conversation 隔离、mid-conversation profile switch、profile mismatch=0、DAX/Answer LLM 调用为 0 与 residual=0 均通过。Fresh Semantic Compatibility `306 passed`、backend `1940 passed, 1 skipped`、frontend `86 passed`、Golden `11 passed, 1 manual-real skipped`，全部治理与 compileall PASS。
- M5.8.2 已完成；M5.8.3 COMPLETE；M5.8.4 COMPLETE（`41b6e0b` 主开发，`a975310` 测试时钟修复，CI #33457056546 completed/success）；完整 M5.9 与 M5.10 保持 NOT STARTED；M5 FINAL=false。

*最后更新：2026-09-02 | M5.8 / M5.8.1 / M5.8.2 COMPLETE；M5.8.3 COMPLETE；M5.8.4 COMPLETE；M5.9 / M5.10 NOT STARTED；M5 FINAL 尚未成立*
