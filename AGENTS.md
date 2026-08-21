# AGENTS.md — PowerBIAgent 仓库级 Agent 入口

> Claude、Codex 与其他代码 Agent 修改文件前必须先读本文件。
> 本文件只提供仓库地图、开发铁律与 Cold Start；当前状态见 `docs/09_context_handoff.md`，路线见 `docs/08_development_roadmap.md`。

## 项目目标与当前阶段

PowerBIAgent 是供公司内部少量用户使用的 Power BI 数据分析 Agent MVP。

当前版本：**M5.1 — React 前端实现与核心联调**。M4.4.2 FINAL PASS；M5.0 文档固化与 M5.1 前端实现已完成；M5.2 NOT STARTED。

- M0—M1 已由 Tag `m1.7.2-m0-m1正式封板` 封板。
- M0—M2 已由 Tag `m2.6.4-m0-m2-final-seal` 在 `70748da` 正式封板；M2 Local MCP + Power BI Desktop 真实链保持不变，Remote MCP 生产化继续 Deferred。
- M2.6.2 已建立 Business Semantic Grounding；M2.6.3 已建立 Deterministic DAX、Independent Layer 3 与 VerifiedFactSet。
- M3.0 已在 `e4b5c6c` 通过远程审计并纯 fast-forward 合入 `main`；对应 main push CI `31986207118` success。
- M3.1 已在 `fa4cc0c` 通过远程审计并纯 fast-forward 合入 `main`；对应 main push CI `31989328261` success，开发分支已删除。
- M3.2 已完成确定性 CSS 横条、静态安全与视觉验收；M3.3 完成 capability-aware section 去冗余布局。
- M3.4 已完成 Adaptive Report Planning：schema-aware capability engine（9 sections）、deterministic ReportPlan、受控 Report Intent weak signal、Visualization/Layout/Theme Policy、Renderer 多 visual（KPI/Line/Donut/Column/HBar）；ADR-011 supersede ADR-010 固定四查询限制；Simple/Rich 双 PBIX Real acceptance 通过。
- M0—M3 已正式封板（Tag: `m3.4-m0-m3-final-seal`）。
- **M4.0** 已建立本地持久化架构与存储基础：SQLite + SQLAlchemy Async + aiosqlite + Alembic 技术栈；`backend/app/persistence/` 包（database.py / models.py / serialization.py）；5 表 schema（conversations / work_memories / pending_clarifications / result_snapshots / report_artifacts）；Alembic migration 基线；`MemoryRepository` / `SnapshotRepository` ABC 抽象；TurnPipeline 不再绑定 `InMemoryMemoryRepository`；ADR-012。
- **M4.1** 已实现 `SQLiteMemoryRepository` + `SQLiteSnapshotRepository` production wiring、DB 级 partial unique index 并发提交 invariant（`ix_work_memories_committed_version`）、严格 concurrent commit 测试。`persistence_backend=sqlite` 提供跨重启持久化。默认 backend 仍为 `memory`。
- **M4.1.1** 已实现 transaction-safe conversation root upsert、Memory/Snapshot 首次创建 race hardening、committed-version partial unique invariant、OperationalError 初步分类、`PersistenceRepositoryError` 异常类。
- **M4.1.2** 已实现 failed transaction 后 fresh-session conflict resolution（`_resolve_locked_commit_failure` helper）、real OperationalError semantics tests（通过 `AsyncSession.execute` 注入）、infrastructure failure 与 business version conflict 严格分离。
- **M4.1.3** 已实现 locked failure 必须在原 transaction 退出后再 fresh-session resolution、真实 SQLite lock integration test、M4.1 series final hardening。
- **M4.2** 已实现会话/报表恢复；M4.2.1 将 HTML authority 固定为 filesystem 并持久化 conversation/request linkage；M4.2.2 完成严格路径 containment 与 row/payload coherence。
- **M4.2.3** 已完成持久化 invariant 最终收口：modern report payload 的 7 个 authority 字段缺失或与 DB row 冲突均 fail closed；`report_id` 为 immutable resource identity，仅完整 metadata 相同可幂等 no-op；conversation report history 固定以 `(source_mode, conversation_id)` 隔离 Mock/Real。M4.2 series FINAL PASS。
- **M4.3** 已实现 SQLite recent/history/search/archive/delete API：所有 conversation 查询/变更必须显式 `(runtime_mode, conversation_id)` namespace，report history 必须显式 `(source_mode, conversation_id)`；history 只组合 persisted result snapshot、同 request committed memory 与严格 report metadata，不声称 message transcript；search 仅覆盖 committed `analysis_goal` 与 snapshot 的 answer/clarification/unsupported 文本；archive 逻辑隐藏，delete 物理清理同 namespace DB rows 与关联 HTML。新增 migration `f4c3a2b1907d`。
- **M4.4** 已完成真实临时 SQLite + report filesystem 的 dispose/fresh-engine restart/crash acceptance：committed Memory 与 terminal Snapshot 可恢复；Memory 存在但 Snapshot 缺失视为 incomplete crash witness 并 fail closed；持久化 report snapshot 不再保存 HTML，重放必须从 filesystem 加载并校验；conversation delete 使用 durable delete intent 跨 DB commit/HTML cleanup 窗口重试，pending intent 阻止同 namespace 复活。新增 migration `c8d4e6f2a109`。**M4 FINAL PASS；M5 NOT STARTED。**
- **M4.4.1** 已修复 committed canonical filter 损坏被静默丢弃的 fail-open：domain 反序列化与 StateTransition 均 deterministic fail closed，发生在 LLM/DAX/Power BI/新 Memory commit 之前；合法 legacy dict filter 与 legacy time string contract 保持不变。根 README 已重构为长期 Landing Page，并同步正式状态文档。无 schema change、无 migration。**M4.4.1 FINAL PASS；M5 NOT STARTED。**
- **M4.4.2** 已完成 M0—M4 truth/persistence boundary 最终代码审计与收口：modern committed WorkMemory 只能从完整 `payload_json` 恢复，NULL/empty/malformed/incomplete/domain-invalid payload 及 row/payload 冲突全部 fail closed，禁止 partial column fallback；conversation-scoped MemoryRepository API 强制显式 runtime namespace，InMemory/SQLite 均严格隔离；terminal Snapshot row/payload integrity 与非 legacy committed time corruption 同样 fail closed。无 schema change、无 migration。**M4.4.2 FINAL PASS；M5 NOT STARTED。**
- **M5.1** 已创建 React + Vite + TypeScript 前端，实现可折叠 Sidebar、欢迎/对话态、Composer、DeepSeek 单选、集中配置的模型/模板菜单，以及 Chat/Recent/Search/History/Reports 真实 API adapters。项目/账户保持纯展示；不新增 discovery endpoint，不修改 M0—M4 truth/persistence authority。现有 Chat/History 不暴露 QueryResult rows/ChartSpec，前端不从审计或文字伪造表格/图表。**M5.1 COMPLETE；M5.2 NOT STARTED。**

当前真实主链：

```text
Natural Language
→ FastAPI / TurnService → TurnPipeline → Intent
→ ToolGateway → PowerBIAdapter → SemanticModelSchema
→ Semantic Grounding + StateTransition → Canonical QueryPlan
→ Deterministic DAX → Independent Layer 3
→ ToolGateway → PowerBIAdapter → Power BI → QueryResult
→ VerifiedFactSet → deterministic Report Data Contract
→ deterministic ReportSpec → Fixed Renderer → static HTML
→ ReportArtifact → report_id / view / download
→ Memory / Snapshot
```

Real DAX LLM authority 为 0。M3 template canonical authority、查询集合、KPI/表格/排名/趋势/因果/事实、HTML/CSS authority 同样为 0。LLM 只保留意图/语言草稿、Catalog-owned 候选内的受限消歧和受事实约束的格式化职责。

## 权威文档顺序

冲突顺序：用户当前明确要求 → `PROJECT_CHARTER.md` → 正式 PRD → Accepted ADR → 当前轮专项设计 → 08 Roadmap → 09 Handoff → `CLAUDE.md` → 代码与 fresh 测试证据 → Archive。

文档地图与按需阅读入口见 `docs/index.md`。不得用聊天记忆或历史 PASS 数字替代仓库和 fresh 证据。

## 每轮固定 Cold Start

固定 P0：`AGENTS.md`、`PROJECT_CHARTER.md`、`CLAUDE.md`、09 Handoff、08 Roadmap、Error Ledger 相关项、ADR index 与当前 ADR。再读取当前 Prompt 指定文档、涉及的生产代码与邻近测试。

不要默认读取完整 `CHANGELOG.md`、`docs/archive/`、全仓源码、全部测试或历史 diff。

## 架构与 Truth Boundary 铁律

1. TurnPipeline 是唯一确定性控制面；Mock 与 Real 共用执行骨架。
2. Power BI 只能经 ToolGateway → PowerBIAdapter；Service/API/LLM 不得直接调用 MCP。
3. Local / Remote 只能替换 Adapter 后的 Provider，不得形成第二套 Pipeline。
4. Real 失败禁止静默回退 Mock；CI 不接真实 Power BI、Token 或 DeepSeek Key。
5. ADR-008：runtime schema、model-scoped glossary、runtime members 与固定时间规则是业务语义来源；Grounding/StateTransition 是 Canonical QueryPlan slot authority。
6. Bounded LLM selector 只能消费 Catalog-owned candidate ID；无足够唯一区分证据必须 AMBIGUOUS/UNRESOLVED。
7. ADR-009：Real 只执行受限 Deterministic DAX；Independent Layer 3 必须在 Power BI 前 fail closed。
8. VerifiedFactSet 是数字、结果顺序、极值、筛选、时间和 provenance 的唯一外部事实 authority；Answer/Report 不得扩写未验证排名、因果或数值。
9. PendingClarificationContext 与 committed Memory 分离；未补齐、歧义、unsupported capability 或失败 Turn 不得提交或污染正式 Memory。
10. `local_mcp.py` 仅负责 Local Provider/protocol Adapter；Renderer、Memory、UI 逻辑不得进入。
11. ADR-010：M3 production template 只有 `sales_report`；TemplateContract 固定 schema 要求，ReportDataPlan 不读取 LLM draft，且每个查询必须复用 M2 封板链。
12. ADR-011：固定模板 = 固定设计规则 + 允许能力目录，不是固定输出内容；报表 section 由用户需求 ∩ runtime schema 能力 ∩ catalog 决定；capability.py 是 schema-aware capability engine；Report Intent weak signal 只输出 registry-owned ID 并单独计数；Visualization/Layout/Theme Policy 由普通代码决定，LLM 无图表选择 authority。
13. M4.3：Repository query/mutation 必须把 namespace 作为必填参数；不得只按 `conversation_id` 查询、归档或删除；SQLite history/search 不是 business/result/report factual authority，也不得从现有 schema 伪造 transcript。
14. M4.4：只有 terminal Snapshot 可作为 request replay authority；Memory-without-Snapshot 必须 fail closed。Report HTML 只能从 filesystem 恢复。跨 DB/filesystem delete 必须保留 durable cleanup intent，cleanup 成功后才能清除 intent。

同时禁止：LangGraph、多 Agent、重新引入 PydanticAI、绕过 Harness、复制 Real Pipeline、提前开发 M5、开发 Remote MCP；未经用户明确批准不得创建 Tag。

## 修改前检查

开始开发前内部确认：职责属于哪个现有模块；能否复用现有接口/Adapter；是否绕过 TurnPipeline/ToolGateway；是否扩大到后续 Milestone。任一边界不清先核实。

## 测试与 Git

- 优先补邻近领域测试；不创建 `test_m2_xxx.py` 式版本型测试。
- 一个 Bug 对应最接近真实生产入口的回归；Real Power BI 只做人工 Smoke。
- 详细修复证据、两次修复上限、Secret、Commit、Tag 规则见 `CLAUDE.md`。
- 禁止 force push、`git reset --hard`、`git add .`、`git add -A`。
- 只用明确白名单暂存；`.env`、Token、PBIX、真实业务输出与 `local_state/` 永不提交。
- 文档与版本必须在 Commit 前完成；`main` 只允许在用户明确授权、fresh gates 全绿且可纯 fast-forward 时更新；不创建 Tag。

## 文档治理

- `docs/00`—`docs/09`、`docs/index.md` 为全局主干；08/09 路径固定。
- 专项规范放 `docs/specs/`；阶段计划放 `docs/milestones/<milestone>/`；ADR 永远放 `docs/adr/`；历史资料放 `docs/archive/`。
- 禁止继续新增 `docs/13_xxx.md`、`14_xxx.md` 等根层编号文档，除非用户明确扩充 00—09 主体系。
- 原始 PRD 只保留于 `docs/archive/original/PRD.md`；正式唯一 PRD 是 `docs/00_product_requirements_document.md`。
- Archive 默认不读；不要为每个 Bug 新建 Markdown。

## README Maintenance Contract

1. `README.md` 是 repository landing page，不是 Changelog 或开发交接文件；保持 Overview → Highlights → How It Works → Truth Boundary → Current Capabilities → Quick Start → Runtime Modes → API → Persistence → Development & Validation → Project Status → Documentation → Scope / Known Limits 的稳定顺序，除非项目结构发生重大变化。
2. 新 Milestone 通常只在真实产品能力变化时更新 Highlights / Current Capabilities / Project Status；启动或配置变化时更新 Quick Start / Runtime Modes。
3. 详细版本记录进入 `CHANGELOG.md`；当前开发上下文进入 `docs/09_context_handoff.md`；路线进入 `docs/08_development_roadmap.md`；架构决策进入 `docs/adr/`。README 不重复这些正文。
4. README 中每项 capability 必须有当前仓库代码或 fresh test evidence；禁止为“看起来高级”加入不存在的 feature、badge、benchmark、platform support 或 API。

---

*最后更新：2026-08-20 | M4.4.2 — M0–M4 Truth / Persistence Boundary Final Closure*
