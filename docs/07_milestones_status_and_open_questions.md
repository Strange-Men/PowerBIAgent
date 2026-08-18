# 07 — 里程碑状态与待确认事项

> **状态：** M4.1 — SQLite 记忆与请求快照持久化
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
| M4.2 | Conversation/Report recovery | ⬜ 未开始 |
| M4.3 | Search/history API | ⬜ 未开始 |
| M4.4 | Restart/crash acceptance | ⬜ 未开始 |
| M5 | React + Vite 前端与联调 | ⬜ 未开始 |

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
| ReportArtifact | ✅ report_id、provenance、content type/hash、原子本地保存 |
| Resource API | ✅ view/download；unknown/path traversal 拒绝 |
| Idempotency / Memory | ✅ replay 复用 report_id；render/store failure 不成功提交 Memory |
| Persistent sessions / React | ⬜ M4.1+ / M5，未提前实现 |
| Persistence Architecture (M4.0) | ✅ ADR-012、SQLite/SQLAlchemy Async/Alembic、5 表 schema、migration 基线、Repository ABC |
| Memory / Snapshot SQLite 实现 (M4.1) | ✅ SQLiteMemoryRepository + SQLiteSnapshotRepository production wiring、DB 级 partial unique index 并发安全、strict concurrent commit tests |
| Conversation/Report recovery | ⬜ M4.2 |
| Search/History API | ⬜ M4.3 |

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

## M4.0 / M4.1 Persistence Architecture changes

- **M4.0**：新增 ADR-012（本地持久化架构）：SQLite + SQLAlchemy Async + aiosqlite + Alembic；`backend/app/persistence/` 包（database.py / models.py / serialization.py）；5 表 schema + UNIQUE + FK；Alembic 迁移基线；Settings 扩展（默认 memory）；Repository ABC；1517 tests。
- **M4.1**：SQLiteMemoryRepository + SQLiteSnapshotRepository production wiring（`main.py` → `MockTurnService`/`DeepSeekTurnService`）；DB 级 partial unique index `ix_work_memories_committed_version`（`WHERE state_status = 'committed'`）保证同 (runtime_mode, conversation_id, memory_version) 最多一个 COMMITTED 行；`commit()` 内 `IntegrityError`/`OperationalError` → `MemoryVersionConflictError`；strict concurrent commit tests（exactly-one-success + 8 轮多轮验证）；corrective migration `ab8d7df39a02`。1559 tests。

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
| M4 持久化介质与会话搜索策略 | M4 开始前 |
| M5 前端状态管理与展示范围 | M5 开始前 |
| Remote MCP 管理员与授权条件 | 重新批准 Remote 后 |

## 当前真实风险

- Simple M3 PBIX runtime `OrderDate` 为 `Int64`；Simple 模型无时间趋势能力（TIME_TREND UNAVAILABLE），不得伪装为 DateTime。Rich PBIX `OrderDate` 为 `DateTime` 且含 Date 表，趋势能力真实解析。
- Capability 目录随 runtime schema 变化；schema 变更需按能力目录重新人工 smoke（不再依赖单一 fingerprint gate）。
- Local Modeling MCP 仍为 Preview；官方包、Desktop 或协议变化后需重新人工 smoke。
- ReportRepository 是 M3 artifact resource，不是 M4 session persistence；进程内 metadata 不承诺跨进程恢复。
- PBIX、真实输出、HTML 与 `local_state/` 永不提交。

## Tag 与基线

| 项目 | 值 |
|---|---|
| M0—M2 Final Seal | `m2.6.4-m0-m2-final-seal` → `70748da` |
| M3.0 main | `e4b5c6c`；CI run `31986207118` success |
| M3.1 main | `fa4cc0c`；CI run `31989328261` success；开发分支已删除 |
| **M0—M3 Final Seal** | **`m3.4-m0-m3-final-seal` → `ff8aca23`** |

---

*最后更新：2026-08-18 | M4.1 — SQLite 记忆与请求快照持久化*
