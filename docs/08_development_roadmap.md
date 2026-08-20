# 08 — 开发路线

> **状态：** M4.4.1 — Memory Corruption Fail-Closed、README 重构与文档状态同步（FINAL PASS）
> **用途：** 只记录当前路线、阶段边界和已封板摘要；逐版本历史见 `CHANGELOG.md`、Git 与 archive。

## 路线总览

| Milestone | 目标 | 状态 |
|---|---|---|
| M0—M1 | Foundation、DeepSeek、统一 TurnPipeline、Harness 与安全治理 | ✅ 已封板 |
| M2 | Local MCP + Power BI Desktop 真实数据问答与 Truth Boundary | ✅ `m2.6.4-m0-m2-final-seal` 正式封板 |
| M3.0 | Report Architecture + Template/DataPlan Contract | ✅ 完成、远程审计 PASS、已合入 main |
| M3.1 | Sales Report Full Generation + Static HTML + Report Resource | ✅ 远程审计 PASS、已合入 main，CI success |
| M3.2 | Hardened visual acceptance / M3 收口阶段 | ✅ 完成，无 Tag |
| M3.3 | Report Template V2 / Non-redundant Business Information Architecture | ✅ 已完成 |
| **M3.4** | **Adaptive Report Planning + Visualization/Layout Policy** | ✅ **已完成** |
| **M4.0** | **本地持久化架构与存储基础** | ✅ **已完成** |
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
| M5 | React + Vite 极简对话前端与联调 | ⬜ 未开始 |

M0—M2 Final Seal 为 `70748daabfa5d3dd250f17fe22f0c892c7a30b74`。M3.0 commit `e4b5c6c6a759cdf22c74c4d87902482563e27cad`、M3.1 commit `fa4cc0c97a10bcc0867c414dc3fa2d7fa9b35e57` 已纯 fast-forward 合入 main，对应 main CI 均 success。M3.2 / M3.3 / M3.4 直接在 main 完成。M0—M3 已正式封板（Tag: `m3.4-m0-m3-final-seal`）。M4.0 已在 main 完成本地持久化架构：SQLite + SQLAlchemy Async + Alembic；MemoryRepository/SnapshotRepository ABC；settings 扩展；26 新增 tests（1503 total）。M4.0 后续 corrective hardening：pytest-asyncio CI 兼容修复、conversation 复合 PK/FK 命名空间隔离、PRAGMA 每连接事件修正；corrective migration `01dc0d90d920`；40 持久化 tests + 全仓 1517 total。

## 永久 M2 事实链

```text
Canonical QueryPlan
→ Deterministic DAX
→ Independent Layer 3
→ ToolGateway → PowerBIAdapter → Power BI
→ QueryResult
→ VerifiedFactSet
```

Real DAX/factual authority 不回到 LLM，Real failure 不回退 Mock。

## M4.4.1 — Memory Corruption Fail-Closed、README 重构与文档状态同步（FINAL PASS）

- `StructuredWorkMemory.filters` 仍保持既有 `list[dict]` storage/legacy contract，但 domain validation 会逐项按 canonical `StructuredFilter` 校验；SQLite payload 的 malformed filter 在 fresh repository load 时 deterministic fail closed。
- StateTransition 不再捕获 malformed committed filter 后 `continue`；进程内出现绕过初始 validation 的损坏状态时抛出稳定 `committed_memory_filter_invalid:<index>`，不得降级为空 filter 或扩大查询范围。
- 真实临时 SQLite restart regression 同时覆盖 Mock/Real namespace：损坏 namespace 在 LLM、schema、DAX、Power BI 与新 Memory commit 前失败；合法 sibling namespace 正常恢复。legacy time string contract 保持不变。
- 根 README 已重构为稳定 Landing Page，并在 `AGENTS.md` 固化 maintenance contract；正式 PRD、07/08/09 与 CHANGELOG 状态同步。无 schema change、无 migration；M5 NOT STARTED。

## M4.4 — Restart / Crash Acceptance & M4 Final Closure（FINAL PASS）

- Acceptance 使用临时真实 SQLite 文件与 report filesystem：runtime A 写入后 dispose engine，runtime B 使用全新 engine/session/repository/service 恢复；没有用同一 Python repository 对象冒充 restart。
- committed Memory 及 version、terminal Snapshot replay/fingerprint conflict、recent/history/search/reports、archive/delete 与 Mock/Real 同 conversation ID 隔离均通过 restart 验收。Pending/Failed 不进入 committed context。
- Snapshot completion boundary：durable terminal Snapshot 即使尚未 complete process-local tracker，重启后仍可 replay；只有 in-flight claim 而无 Snapshot 时不产生 completed。Memory 存在但 Snapshot 缺失表示无法安全确认外部副作用，TurnPipeline 以 `IdempotencyCoordinationError` fail closed，不重执行、不生成 terminal duplicate。
- Report recovery boundary：新 persistent report Snapshot 只存 ID/reference/hash metadata，不存 HTML；replay 必须经 ReportRepository 从 filesystem 读取，并验证 metadata、linkage、namespace 与 content hash。验收修复了 adaptive Real report 错传未带 conversation/request context 的原 `ReportSpec`；missing/tampered HTML、corrupt metadata 或 linkage mismatch fail closed。
- Delete recovery boundary：migration `c8d4e6f2a109` 新增 `conversation_delete_intents`。DB 删除 transaction 同时保存 exact namespace 的 report IDs/counts；HTML cleanup 成功后才 finalize。unlink/finalize failure 或中间 crash 后，全新实例可按同 namespace 重试；pending intent 阻止 namespace 复活。SQLite transaction 不被描述为可原子覆盖 filesystem。
- Bounded guarantee：report create 的常规 metadata-save failure 会 best-effort unlink 已写 HTML；本轮未增加 durable create journal，因此不保证进程恰在 HTML rename 后、metadata commit 前退出时自动回收无引用文件。该窗口没有 metadata/Snapshot 成功态，读取仍 fail closed。
- Fresh DB → head、M4.3 `f4c3a2b1907d` → head、backend `1681 passed, 1 skipped` 均通过。M4 FINAL PASS；M5 NOT STARTED；不创建 Tag。

## M4.3 — Conversation History / Search API（已完成）

- 新增 `ConversationHistoryRepository` 抽象、SQLite 实现与 application query service；API/router 不直接访问 SQLAlchemy。SQLite 仍只是 persistence provider，不是 business/result/report factual authority。
- Conversation identity 为 `(runtime_mode, conversation_id)`；recent/history/search/archive/delete repository 方法的 `runtime_mode` 均为必填。Report history identity 为 `(source_mode, conversation_id)`，不得只按 `conversation_id` lookup/cascade。
- recent 只返回 unarchived conversations，排序固定为 `updated_at DESC, conversation_id ASC`；terminal snapshot 在同一 transaction touch exact conversation root。所有列表 page size 为 1—50，opaque keyset cursor 绑定 endpoint、namespace、search query 与 resource。
- history 是结构化 persisted view：`result_snapshots` 是 terminal turn ledger，同 request committed `work_memories` 只补充 analysis/model/version fields；report history 复用 M4.2.3 strict reconstruction。DB 没有逐字 message transcript，因此 API 不生成 transcript，也不暴露 HTML/ORM/payload JSON。
- search 不引入 FTS5；只对 committed `analysis_goal` 和 snapshot `answer` / `clarification_question` / `unsupported_reason` 做 deterministic SQLite contains query。Report HTML、DAX、任意 JSON 全文、未存储 prompt 均不在 search scope。
- archive 为幂等逻辑隐藏：从 recent/search 排除，但 direct history/reports 继续可读。delete 为物理删除：transaction 内清理同 namespace work memory/snapshot/pending clarification/report metadata/conversation root，随后由 report repository 删除同 source_mode 的精确 HTML 文件；另一 namespace 不受影响。Unknown conversation 一致 404。
- Migration `f4c3a2b1907d` 新增 nullable `conversations.archived_at` 与 recent/history/report namespace 复合索引；fresh DB 与 M4.2.3 schema upgrade 均通过。其 restart/crash 行为已由 M4.4 验收。

## M4.2.3 — Persistence Invariant Final Closure（已完成）

- `payload_json` 是 modern metadata reconstruction authority，DB dedicated columns 是 immutable integrity witness。payload 必须显式包含 `report_id`、`template_key`、`semantic_model_key`、`schema_fingerprint`、`source_mode`、`content_hash`、`relative_path`，且与 columns 严格一致；缺失或冲突均 `ReportStorageError` fail closed，不使用默认业务值或 derived path。
- `conversation_id` / `request_id` nullable；DB 有值时 payload 必须显式存在且一致。
- `report_id` 是 immutable resource identity；SQLite 与 InMemory repository 语义一致：完整 metadata 相同为幂等 no-op，任一 metadata/provenance/linkage 不同为 collision，禁止 overwrite。
- `source_mode` 仅允许 `mock | real`；M4.3 的 conversation → reports 查询必须使用 `(source_mode, conversation_id)` namespace，禁止 Mock/Real 串历史。
- 现有 report table 的 `source_mode` 与 `conversation_id` 已由 M4.3 report history/delete 查询直接作为 namespace predicate；未引入 FTS5。

## M3.4 — Adaptive Report Planning + Visualization/Layout Policy（已完成）

根因修复：M3.3 之前"固定四查询、固定两种横条、无法根据自然语言和语义模型能力生成不同报表"。M3.4 修复的是**报表规划能力**，不是 HTML/CSS。ADR-011 supersede ADR-010 的"一个 template 永久绑定一个 fingerprint + 固定四 queries"限制；ADR-010 的固定事实安全边界继续有效。

- 固定模板新定义：固定设计规则 + 允许能力目录（Design System / Allowed Section Catalog / Visualization Policy / Layout Policy / Theme Policy / Security Rules），不是固定输出内容。
- 最终 section 由"用户自然语言需求 ∩ runtime semantic capability ∩ sales_report allowed catalog"确定；"只看销售额"→ 单 KPI 报表，"生成完整销售分析报表"→ 能力驱动 dashboard。
- 新增 schema-aware capability engine（9 个 registry-owned sales capabilities：SALES_KPI / QUANTITY_KPI / ORDERS_KPI / AOV_KPI / TIME_TREND / CATEGORY_CONTRIBUTION / REGION_COMPARISON / TOP_PRODUCTS / TOP_CUSTOMERS）；缺能力 fail closed，绝不 Mock/占位。
- 新增受控 Report Intent weak signal：LLM 只输出 registry-owned section ID，未知 ID 丢弃，确定性匹配器是地板，"只看…"忽略 LLM 增量；单独计数 `llm_report_intent_call_count`。
- 新增 deterministic ReportPlan（requested / resolved / unavailable sections、去重 query requirements、provenance）→ 查询子集 → 复用 M2 密封链。
- 新增 VisualizationPolicy（KPI Card / Line / Donut≤8 / Column / HBar，禁止所有 grouped→hbar）、LayoutPolicy（KPI 行 → 全宽趋势 → 2 列对比/排行对）、ThemePolicy（dataviz 验证调色板）。
- `SalesReportRenderer`（原 FixedSalesReportRenderer 更名）支持 charts：inline SVG line/donut、CSS column/hbar、KPI cards；无 JS/CDN/外部资源。
- 时间趋势来自 Power BI query → QueryResult → VerifiedFactSet；Renderer 不聚合；只对已验证时间点做确定性显示排序。
- 最小通用扩展：`CanonicalQueryPlan.dimension_tables` / `dimension_order`（star-schema 重名列消歧；None 时 M2 行为不变）；ChartSpec 增加结构化 `visual_type` / `business_role` / `series` / `layout_hint`。
- 双模型 Real acceptance：Simple PBIX 保持 M3 基线四查询行为；Rich PBIX（fingerprint `31505f79...`）解析 9 sections / 9 查询，4 种 visual，全部真实事实；事实类 LLM counters 全 0。

## M3.3 — Report Template V2 / Non-redundant Information Architecture（已完成）

M3.3 未新增业务查询、DAX、filter、template、LLM authority 或事实来源；重构 sales_report 信息架构，引入 capability-aware section 设计。

- 新增 `backend/app/report/capability.py`：SectionCapability 概念（M3.4 已重构为 schema-aware capability engine，见上）。
- `FixedSalesReportRenderer` 改为 section-capability 感知渲染：每 section 只保留一种主要视觉表达（horizontal bar），移除与 bars 重复的同源明细 table。
- `sales_report.html` 模板重写：双列 KPI → 品类 bars → 产品 bars → metadata footer；响应式窄屏 Flex 换行；无 JS/CDN/外部资源。
- 多语义模型防伪测试：Model A 当前 schema 所有 section 正常；Model B 多 Date/Region/Customer 字段不自动生成 section；Model C 缺 Category/Product 时 contract validation fail closed。

## M3.2 — 已完成 hardened visual acceptance

M3.2 未新增模板、查询、DAX、业务语义、图表类型、资源 API、前端或持久化能力；只把 M3.1 已有 Category / Top Product `ChartSpec` 与同源 table rows 以固定 CSS 横条呈现，并完成静态安全、Real PBIX、桌面/430px 视觉、文档与 CI 收口。

## M3.0 — 已完成合同基线

- 唯一 production template 为 `sales_report`；legacy keys 仅历史 Mock compatibility，production unavailable。
- TemplateContract 绑定 `local_desktop_model` 与 M3 PBIX fingerprint（M3.4 起 fingerprint 不再是 contract gate，见 ADR-011）。
- ReportDataPlan 固定四查询（M3.4 起由 capability 解析决定查询子集）。
- 缺对象、类型、model mismatch 时不生成 partial plan。

## M3.1 — 已完成正式生成链

### 唯一正式链（M3.4 更新）

```text
Natural Language / Template Grounding
→ Bounded Report Intent weak signal
→ deterministic ReportPlanner → Canonical ReportPlan
→ N × CanonicalQueryPlan → N × Deterministic DAX + Independent Layer 3
→ N × ToolGateway → PowerBIAdapter → Power BI
→ N × QueryResult → N × VerifiedFactSet
→ deterministic SalesReportData
→ deterministic ReportSpec（VisualizationPolicy 选 visual）
→ SalesReportRenderer（design system）→ static UTF-8 HTML
→ ReportArtifact / ReportRepository
→ report_id / view / download
→ Memory / Snapshot
```

### Fixed sales content（M3.4 更新）

- 标题：销售分析报表。
- Section 由用户需求 ∩ runtime capability 决定；完整能力时：4 KPI（总销售额/总销量/总订单数/平均订单金额）→ 月度销售趋势 → 品类销售贡献 → 区域销售对比 → Top 5 产品 → Top 5 客户。
- Metadata：数据来源、source_mode、contract version、generated_at。
- TopN 仅显示 `result_position`；不制造严格业务名次、趋势或原因分析。

### Resource contract

- `ReportArtifact` 固定 report_id、template/contract/model/fingerprint、N 组 QueryResult/FactSet IDs、source_mode、content type/hash 与 created_at。
- 正式 HTML 原子保存于 `local_state/reports/<report_id>.html`；验收副本只能复制同一 Renderer 输出到 `m3_sales_report.html`。
- `GET /api/reports/{report_id}` 查看；`GET /api/reports/{report_id}/download` 下载。
- 同 request_id 重放只读 Snapshot，复用同一 report_id，不重新执行 Power BI 或生成第二 artifact。

### Truth Boundary（M3.4 更新）

LLM 对 template canonical authority、查询集合、CanonicalQueryPlan factual slots、DAX、KPI/rows、结果顺序、趋势、因果、Report factual truth、HTML/CSS、chart data 和 report reference 的 authority 均为 0。LLM 唯一新增：Report Intent weak-signal draft（registry-owned section ID），单独计数。

## 永久阶段边界

- 不使用 LangGraph、多 Agent 或 PydanticAI。
- 不复制 Pipeline/Service，不绕过 TurnPipeline、ToolGateway、PowerBIAdapter、Independent Layer 3、VerifiedFactSet 或 Memory/Snapshot。
- 当前报表针对各 PBIX 全量数据；不新增动态月份、Category filter、comparison、用户自由 ReportDataPlan 或任意 DAX。
- M3 不做 PDF、自由 HTML、用户模板、JavaScript、复杂图表框架、React UI 或 Remote MCP。
- M0—M3 已正式封板（Tag: `m3.4-m0-m3-final-seal`）；M4 backend 已在 M4.4 FINAL PASS，M4.4.1 corrective closure FINAL PASS；未经用户另行明确批准不得进入 M5；禁止 force push。

---

*最后更新：2026-08-20 | M4.4.1 — Memory Corruption Fail-Closed、README 重构与文档状态同步*
