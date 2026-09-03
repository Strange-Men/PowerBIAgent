# AGENTS.md — PowerBIAgent 仓库级 Agent 入口

> Claude、Codex 与其他代码 Agent 修改文件前必须先读本文件。
> 本文件只提供仓库地图、开发铁律与 Cold Start；当前状态见 `docs/09_context_handoff.md`，路线见 `docs/08_development_roadmap.md`。

## 项目目标与当前阶段

PowerBIAgent 是供公司内部少量用户使用的 Power BI 数据分析 Agent MVP。

当前版本：**M5.8.5 — Semantic Completeness + Result Inspection + Presentation Truth（COMPLETE）**。现有唯一语义链新增 Semantic Obligation Coverage、Canonical Shape Completeness、Result Semantic Inspection 与 Deterministic Query Scope 四个 correctness invariant；三 PBIX × DeepSeek/Kimi Real 定点链、2,304-case stress、全量本地门禁与 automation-owned residual=0 已通过。本提交 exact-SHA CI 作为发布证据；M5.9/M5.10 NOT STARTED，M5 FINAL=false。

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
- **M5.1** 已创建 React + Vite + TypeScript 前端，实现可折叠 Sidebar、欢迎/对话态、Composer、DeepSeek 单选、集中配置菜单，以及 Chat/Recent/Search/History/Reports 真实 API adapters。项目/账户保持纯展示；现有 Chat/History 不暴露 QueryResult rows/ChartSpec，前端不从审计或文字伪造表格/图表。**M5.1 COMPLETE。**
- **M5.2** 已完成 Real 业务链路与前端逻辑收口：新增只读 `GET /api/v1/semantic-models`，前端动态使用后端 Desktop safe catalog/runtime namespace；SQLite conversation/restart/recent/search/history/report 已真实联调；`report_template_key` 仅为显式可选 override，未传时 report intent 由后端选择 registry-owned 默认 `sales_report`；完成 7-turn Real acceptance、最小错误分类和结构化表格/图表契约审计。**M5.2 COMPLETE。**
- **M5.2.1** 已收口 discovery capability truthfulness：Mock discovery 只暴露可进入正式 Chat pipeline 的 `mock_sales_model`，`mock_satisfaction_model` 保留为测试 fixture 但不再作为正常可选项；Real Local MCP discovery 合同不变。根 README 增加醒目的本地 Power BI 真实模式启动说明，并与 `frontend/README.md` 统一中文表达。**M5.2.1 COMPLETE。**
- **M5.3** 已实现安全启动诊断、Desktop 模型最小 compatibility、展示型 transcript/title/rename、conversation 管理、QueryResult/VerifiedFactSet 直接来源的 `presentation` contract、动态指标/表格/柱状图/折线图/报表附件，以及 responsive/accessibility/状态视觉收口。完整 schema fingerprint 仅用于 drift 诊断，不单独阻断模型；Rich PBIX Real 六轮问答、表格、报表、recent/history/search、查看/下载验收通过。M0–M4 factual authority 与 M4 durable delete intent 不变。**M5.3 COMPLETE。**
- **M5.3.1** 已将 Local MCP Desktop contract 收紧为每个 discovery/schema/member/DAX session 只接受唯一实例，多个实例在 Connect 前 deterministic fail closed；`presentation` dataset 仅投影 VerifiedFactSet 数据事实 `source_fields` 覆盖列。无新 registry、无 M0–M4 authority 变化。**M5.3.1 COMPLETE。**
- **M5.3.2** 已升级为多 PBIX 安全枚举与选择：后端生成不泄露连接属性的 deterministic opaque key；schema/member/DAX 每个 session 重新枚举并精确匹配唯一实例；逐 option 只读 MCP capability probe、stale fail-closed 与 DAX row shape/truncation 防腐完成。Remote MCP 继续 Deferred；无 migration、无 M0–M4 authority 变化。**M5.3.2 COMPLETE。**
- **M5.3.3** 已完成多轮与资源生命周期最终收口：当前明确表达 > bounded LLM semantic draft > committed Memory；fresh/follow-up/replace 分离，unsupported 在 Memory/Grounding/DAX 前 fail closed；archive 可恢复且不等于 delete；report 只可由用户显式资源 API 独立删除；前端 history 使用 abort/generation/active identity 防串窗；local_state 与测试 artifact 由长期 ownership/cleanup gate 治理。新增 migration `e7a9c2d4f631`；Rich PBIX 八轮 Real 浏览器与资源生命周期验收通过。M0–M5 factual authority 不变。**M5.3.3 COMPLETE。**
- **M5.4** 已完成 conversation-scoped UI/runtime state、client UUID provisional conversation、异 conversation 并发/同 conversation 串行、Sidebar pending row、用户卡片资源管理、最多 20 项 bounded bulk orchestration、report tombstone 与 presentation-only `display_title`。新增 migration `a4f6b8c2d190`；Rich PBIX A/B/C 并发、归档恢复、rename/delete/history tombstone 与资源清理 Real Browser Acceptance 通过。M5.5 语言理解、中文字段、性能、HTML 视觉继续 Deferred。**M5.4 COMPLETE。**
- **M5.4.1** 已完成 Settings 独立全量 cursor pagination、active/archived conversation/report 管理、准确 total/loaded/selected 语义与最多 20 项一组的 bounded execution；同秒 SQLite cursor 使用 `julianday + stable ID` 防止重复页。automation-owned 资源显式登记 ownership，`finally` teardown 后验证 conversation/report/HTML/SQLite/delete-intent residual 为 0；无法证明 ownership 的现有资源一律保留。新增 migration `b7c9d2e4f610`。**M5.4.1 COMPLETE；M5.5 Deferred。**
- **M5.4.2** 从 M5.4.1 commit `cab40b076f054a3ebdab0bf6d2b0354f4b2d49db` 建立 `m5/rebuild`。旧 `m5/frontend` 的 `a197db3`（原 M5.5）与 `6d1620a`（原 M5.5.1）作为实验/审计记录保留，不删除、不重写、不整体 cherry-pick；新 M5.5—M5.10 必须分域重新实现并重新 Real Acceptance。本轮只做 Git 基线与文档/治理固化，不修改生产业务逻辑。**M5.4.2 COMPLETE。**
- **M5.5** 已完成 semantic correctness、capability boundary、multi-turn slot inheritance、runtime object/member authority、ranking/TopN 与 temporal semantics 的独立重建。explicit unresolved member 已稳定 clarification/no-match 且 ZERO DAX/QueryResult/Memory commit；Sales、Education、Inventory、未知 holdout、schema mutation、Real Rich PBIX 四轮与浏览器人工验收通过。无 schema/migration、Presentation、Report、Resource UX 或 MCP performance 变化。**M5.5 COMPLETE；semantic authority 已冻结。**
- **M5.6** 已完成 canonical/display 分离、model/object/schema-scoped Localization、deterministic presentation formatting、Answer/Table/Chart 信息密度、Recent/Settings resource truth、failed conversation lifecycle、共享 floating action menu 与 Settings nested scroll/toolbar。**M5.6 COMPLETE。**
- **M5.7** 已完成现有 `sales_report.html` 的简易模板可读性、响应式视觉与 `Report Template Required` fail-closed Gate。任何 report intent/request 必须显式携带有效 `report_template_key`；缺失、unknown 或 stale template 均在 ReportData/ReportSpec/Renderer/HTML artifact 之前停止。**M5.7 COMPLETE。**
- **M5.7.1** 已统一语义可靠性、回归防火墙与高强度问答验收；修复 M5.5—M5.7 暴露的语义回归，并建立所有后续版本必须复用的永久 Semantic Compatibility Gate。**M5.7.1 COMPLETE。**
- **M5.7.2** 已将 Report Template Gate 集中前移至 Intent 后、任何 schema/QueryPlan/DAX/ReportData/ReportSpec/Renderer/artifact 前；建立后端 Template/Renderer Registry 与只读模板目录 API，前端改为消费后端目录并清理 stale selection；简易模板完成 4 KPI、趋势、区域/品类、Top 产品、关键明细、footer 的固定信息架构，以及 Y 轴、nice ticks、gridlines、15 月完整桌面标签和确定性小屏跨年双层 tick。**M5.7.2 COMPLETE。**
- **M5.8** 已完成共享 `OpenAICompatibleLLMProvider`、不可变 `LLMModelProfile`、DeepSeek + Kimi-K2.6、request/conversation-scoped model selection、统一 error/usage/trace 与前端模型选择器。Rich PBIX 双模型 canonical/result、并发隔离、mid-conversation switch、unknown/unsupported、固定报表与 residual=0 验收通过；未混入 MCP 性能优化。**M5.8 COMPLETE。**
- **M5.8.1** 已完成前置性能加速与本地 MCP 会话复用：安全 monotonic profiling、application-owned Local MCP session reuse、非事实 metadata/member 短 TTL bounded cache、per-key async singleflight 与最小 MCP 并发保护均已落地；未引入 Redis，未缓存答案/QueryResult/VerifiedFactSet/DAX 结果/Canonical QueryPlan，M5.8 Provider 与 Semantic/DAX/Report authority 保持冻结。**M5.8.1 COMPLETE。**
- **M5.8.2** 已完成 code-owned Question Router、通用 Query Shape、shape-specific required slots、minimal clarification、安全 calculator/help/system-info、dimension-only distinct、Top1、runtime-validated member set/`IN_SET` 与 bounded month trend；非业务 turn 在 schema/member/DAX 前终止且不污染 semantic Memory。M5.8.1 保持冻结。**M5.8.2 COMPLETE。**
- **M5.8.3** 已实现 MCP-driven ModelSemanticContext 与任意 PBIX 通用语义适配。MCP runtime schema 是结构 authority；immutable context 只适配 metadata；exact identity + fingerprint 验证的 override 只补充业务语言；LLM 只在 runtime-owned candidates 中选择。Rich/zero-config/双 PBIX/facts/performance/local full gates 已通过；受控 temp 生命周期已自动化；**正式 COMPLETE 以对应提交的 CI success 为条件**。
- **M5.9** 只负责 MCP profiling、session reuse、cache、bounded concurrency、bounded queue/backpressure、20/50/100 concurrency 与 restart/fault/soak；不得修改 Semantic/DAX/VerifiedFactSet authority。**M5.9 NOT STARTED。**
- **M5.8.4** 已在现有 ModelSemanticContext/SemanticCatalog/Grounding 内完成跨语言对象/成员绑定与 canonical KEEP/REPLACE 优化；report template choice 不等于本轮 report intent。LLM 仅在 runtime 已证明存在的候选 ID 中解释语言，不能产生新对象或事实。`41b6e0b` 主开发后，首次 CI [#33455159267](https://github.com/Strange-Men/PowerBIAgent/actions/runs/33455159267) 因测试 reference date 漂移失败；`a975310` 修复测试时钟后，CI [#33457056546](https://github.com/Strange-Men/PowerBIAgent/actions/runs/33457056546) completed/success；`3e3d8ac` 最终治理 CI [#33580808379](https://github.com/Strange-Men/PowerBIAgent/actions/runs/33580808379) exact-SHA completed/success，M5.8.4 COMPLETE。M5.9/M5.10 不启动。
- **M5.8.5** 已在现有链加入四个通用 correctness Gate；unknown/known+unknown member、残缺 shape、Result 语义不一致均在事实/执行边界 fail closed，TopN tie-break、trend ASC、table/chart 共序与完整 effective scope 均由确定性合同约束。Rich Sales、M3 Test、Logistics Test 的双 Provider Real 与 A→B→C→A 隔离通过；无第二套 authority、无 migration、无 M5.9/M5.10 工作。**M5.8.5 COMPLETE。**
- **M5.10** 只负责“简易模板/销售模板”显式选择与固定专业销售模板；两者都遵守 `VerifiedFactSet → ReportData/ReportSpec → template_key → deterministic fixed renderer`。**M5.10 NOT STARTED。只有 M5.10 全部门禁完成后才允许声明 M5 FINAL。**

当前真实主链：

```text
Natural Language
→ FastAPI / TurnService → TurnPipeline → Intent
→ ToolGateway → PowerBIAdapter → SemanticModelSchema
→ Semantic Grounding → Semantic Obligation Coverage → StateTransition
→ Canonical QueryPlan → Canonical Shape Completeness
→ Deterministic DAX → Independent Layer 3
→ ToolGateway → PowerBIAdapter → Power BI → QueryResult
→ Result Semantic Inspection → VerifiedFactSet → deterministic Query Scope / Presentation
→ deterministic Report Data Contract
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
15. M5.3.3：同 conversation 不等于自动 follow-up；Memory 只继承当前轮真正省略的兼容槽。fresh question 清除无关旧槽，replace 只替换明确槽，证据不足 clarification。semantic model 切换不得继承旧模型业务上下文。
16. M5.3.3：预测、写入、PBIX/Measure 修改、删除数据、任意代码与自然语言 report delete 必须在 committed Memory/Grounding/DAX 前 readonly fail closed；存在 Memory 不是放行理由。
17. M5.3.3：archive 保留 conversation/history/report/HTML 并可 restore；独立 report delete 只能由用户显式 UI/API 触发，不注册 ToolGateway，LLM 无权限。
18. M5.3.3：异步 history 响应必须复核 active conversation 与 request generation；local_state 只允许 persistence/reports/runtime/archive，测试 artifact 必须登记 ownership、teardown 并验证 cleanup，Gate 不自动删除用户数据。
19. M5.4：前端必须以 `conversation_id → ConversationSession` 管理 messages/pending/sending/history/error/status；`activeConversationId` 只决定当前可见会话，不得用单一全局 sending/loading/error 串窗。
20. M5.4：首次发送前端生成符合现有合同的 UUID 并直接作为 Chat `conversation_id`；发送后立即显示 local pending row。不同 conversation 可并发，同一 conversation 仍必须串行；navigation/history 可取消，business chat 不得因切窗取消。
21. M5.4：用户卡片是设置/已归档/资源管理入口；Sidebar 不堆叠批量 checkbox。批量管理只能 bounded 协调现有正式单资源 API，部分失败必须逐项呈现，禁止 `DELETE ALL` 或绕过 durable delete。
22. M5.4：report delete 保留 presentation tombstone；report `display_title` 只是可变展示 metadata，不得修改 `report_id` / HTML / `content_hash` / ReportSpec / VerifiedFactSet。rename/delete 仅由明确 UI 用户操作触发，不注册 ToolGateway，LLM 无权。
23. M5.4.1：Sidebar Recent 只服务轻量导航；Settings 是完整资源管理入口，必须使用独立、namespace-scoped、可持续分页的 conversation/report 查询，不得复用 `recentConversations` 或把第一页冒充全部历史。
24. M5.4.1：“全选当前已加载”只选择已加载行；只有基于明确后端查询条件与完整 ID 集合时才可称“选择全部匹配项”。UI 必须显示 total、loaded 与 selected 数量，全部历史可分页浏览且不得一次渲染无限 DOM。
25. M5.4.1：浏览与选择数量不限于 20；单次 destructive execution wave 最多 20 项，前端可把一次用户确认的大批量操作自动分组，继续逐项调用正式单资源 API并精确汇总 partial failure。禁止 `DELETE ALL`。
26. M5.4.1：Codex acceptance、pytest integration、browser/Real Smoke/MCP/report tests 创建的 conversation/report/file 必须携带可审计 test ownership（至少 test run identity 与 automation owner），在 `finally` 中通过正式 API/repository cleanup 并验证零残留。cleanup failure、pending intent、orphan 或本轮 test SQLite namespace residual 必须使 Gate FAIL。
27. M5.4.1：test cleanup 只能处理已证明 automation-owned 的资源；标题、问题文本或“看起来像测试”不是 ownership 证据。不得删除无法确认 ownership 的用户资源；M5.5 继续 Deferred。
28. M5.4.2：新开发线唯一基线为 `cab40b0`；原 M5.5/M5.5.1 只保留为实验历史与单项设计参考。任何新能力必须重新实现、重新回归并重新 Real Acceptance，旧 PASS 不得移植为新线证据。
29. M5.5—M5.10 必须依次隔离为 Semantic correctness、Presentation/Localization/Resource UX truth、简易报表视觉与模板必选、LLM Provider/双模型、MCP performance/resilience、固定专业销售报表模板与两模板选择。一个 milestone 禁止同时大规模修改 Semantic、MCP、LLM Provider、Presentation、Report、Resource lifecycle 多个域。
30. explicit unresolved semantic requirement 必须 clarification/no-match 且 ZERO DAX；不得把未知 member/filter（例如“火星区”）静默降级为全国或无筛选查询。当前明确表达与 runtime member authority 优先于旧 Memory。
31. PowerBIAgent 不是 Sales Agent。影响泛化的版本必须至少验证 Sales/Retail、Education、Inventory/Operations，并以未知业务模型做最终 holdout；生产代码不得在正式 model-scoped glossary/test fixture 之外写死业务字段、member 或答案。
32. 每轮必须执行 `Spec → Failure reproducer → Regression tests → Minimal implementation → Focused Real → Cross-domain → Full gates → User manual acceptance → commit`。自动化通过数不能替代 Real Browser/人工验收；只有 M5.10 全部门禁完成后才允许声明 `M5 FINAL`。完整合同见 `docs/specs/13_m5_generalization_and_acceptance_contract.md`。
33. M5.6 必须以 conversation/report 共用 Portal/floating layer 解决 action menu 裁切，并以 viewport-aware above/below positioning 避开 scroll container、scrollbar 与 stacking context；Settings Resource Manager 必须有 nested scroll contract 与 sticky 或 scrollable action toolbar。正式 Layout Gate 覆盖 first/middle/last row、scroll top/middle/bottom、100%/125% zoom、768/1080/1440 viewport height、Sidebar scroll、Settings nested scroll，并证明 destructive action 始终可达、floating menu 永不裁切。M5.6 不得修改 Grounding/DAX/MCP authority。
34. M5.10 晚于 M5.9，新增“简易模板”与“销售模板”的显式选择；两者都必须遵守 `VerifiedFactSet → ReportData/ReportSpec → template_key → deterministic fixed HTML renderer`。专业销售模板可使用 sales-specific section，但不得伪造 Forecast/Goal/Pipeline，LLM 不拥有 HTML layout、query 或 factual authority。
35. M5.6：`canonical_name`、runtime object identity、QueryResult/VerifiedFactSet value 与 provenance 永不因本地化改变；`display_name` 只属于 presentation。Localization key 至少包含 semantic model、object identity、object type、locale 与 schema identity，schema/object identity 变化必须使旧 display cache 失效；LLM 只可翻译 runtime 已证明存在的 bounded object candidate。
36. M5.6：展示职责固定为 `Answer = 结论/洞察`、`Table = 精确明细`、`Chart = 趋势/关系`。single scalar 只显示自然语言文本；grouped 使用简短结论与 table，必要时附 chart；trend 使用简短趋势结论、table 与 line。不得逐行复述 table、泄漏 raw timestamp 或重复堆叠相同事实。
37. M5.6：Settings 与 Sidebar Recent Reports 必须读取同一正式 report resource source，Sidebar 仅做 active、bounded、newest-first projection；conversation 排序固定为 `updated_at DESC, created_at DESC, stable_id DESC`，不得依赖 array insertion order。
38. M5.6：failed conversation 是正式、可持久化用户资源，必须支持 Settings 可见、rename、archive、restore、delete；failed turn 仍不得提交 Memory。resource 状态只能来自正式 metadata，不得按 title、用户名或“测试”字样推断。
39. M5.6：conversation/report 共用 `FloatingActionMenu` Portal positioning contract；Settings shell 固定 header、navigation、content scroll、toolbar 与 list scroll 责任。M5.6 禁止修改 Grounding、DAX、MCP、report renderer 或 M5.10 template。
40. M5.7：任何 report intent/request 必须显式拥有 registry-valid `report_template_key`。missing/invalid/stale template 必须 clarification/template-required 且 ZERO ReportData assembly、ZERO ReportSpec、ZERO renderer、ZERO HTML artifact；禁止默认 `sales_report`、猜模板或 fallback 第一项。当前唯一公开模板 `sales_report` 的展示名固定为“简易模板”。
41. M5.7：前端 template selector 只提供显式 choice，不判断用户 intent、不增加 Chat/Report 模式切换；未选模板时不得发送 report request 的隐式 default。Renderer 只消费已验证 ReportData/ReportSpec，不计算业务指标、不查询 Power BI、不调用 LLM、不修改 Memory。
42. M5.8：只允许 `OpenAICompatibleLLMProvider`、`LLMModelProfile`、DeepSeek/Kimi-K2.6 与 request/conversation-scoped model selection；共用同一 authority/regression contract，现已完成并冻结。
43. M5.8.1：只允许安全 profiling、application-owned Local MCP session reuse、tool/discovery/probe/schema/member 短 TTL bounded cache、per-key async singleflight 与最小 bounded concurrency；禁止 Redis、factual result cache、Semantic Plan cache、语义/DAX/Provider/Report/前端业务改动。M5.8.2 已完成自然语言路由与通用 Query Shape；M5.8.3 已实现 MCP-driven ModelSemanticContext 与任意 PBIX 通用语义适配；验收 temp lifecycle 自动化，正式 COMPLETE 以对应提交 CI success 为条件。
44. M5.9：保留完整 MCP performance/resilience：bounded queue/backpressure、20/50/100 concurrency、restart/fault matrix 与 soak；禁止修改 Semantic/DAX/VerifiedFactSet authority。
45. M5.10：只允许固定专业销售模板与“简易模板/销售模板”显式选择；禁止 LLM 临场生成 HTML/CSS/SVG。只有 M5.10 全部门禁完成后才允许声明 M5 FINAL。
46. M5.7.1：日期角色选择优先级固定为用户显式指定 → model-scoped metadata → runtime relationship/default temporal role（仅在可唯一证明时）→ clarification。不得以“模型只有一个 Date/DateTime 字段”为正常执行前提，也不得在多日期角色无唯一证据时猜测。
47. M5.7.1：benchmark 问题、expected 数值与问题→答案映射不得进入 `backend/app/**` production text/code。Gate 必须覆盖 `.py/.yaml/.yml/.json/.toml`，排除 harness/tests/docs/generated/cache/artifact，并禁止 production import/read/depend on known-answer cases、baseline、oracle 或 test-only truth；合法 model-scoped alias/runtime metadata 不得因裸业务词误报。永久 Semantic Compatibility Gate 同时检查 unresolved/invalid member ZERO DAX、time、multi-turn、unsupported、schema mutation、frontend/provider 无 semantic authority。
48. M5.7.1 不开发报表视觉、Template/Renderer Registry、DeepSeek/Kimi Provider 或 MCP performance；M5.7.2 已在 Report Template Architecture 与简易模板质量边界内完成，M5.8 已在独立 Provider/Profile 边界内完成。
49. M5.8.5：Grounding 后所有影响结果的 explicit semantic obligation 必须闭合为 RESOLVED / EXPLICITLY_CLEARED / UNSUPPORTED / NEEDS_CLARIFICATION；未知 member 或 known+unknown set 不得静默丢弃或部分执行，未闭合时 ZERO DAX。
50. M5.8.5：StateTransition 后必须按 QueryShape 验证 CanonicalQueryPlan 必需槽；QueryResult 到 VerifiedFactSet 前必须验证 ranking row count/order/tie-break、trend time/range、entity distinct 与 exact model/scope lineage，失败不得由 Answer LLM 或 presentation 解释过去。
51. M5.8.5：Ranking 的 DAX selection/final ORDER BY、QueryResult、inspection、table/chart 必须保持同一 canonical order；普通 grouped metric DESC 与 trend time ASC 只能是共享 PresentationDataset projection，不得修改 QueryResult/VerifiedFactSet。effective scope 必须由最终 plan/localization 确定性生成并进入可见 Answer。
52. M5.8.5：显式 fresh cue 高于旧 PendingClarification、Memory 与 LLM relation draft；follow-up 只继承真正省略且兼容的 canonical slot，replace 只替换明确 slot。禁止用无限 regex、PBIX 名称或领域 hardcode 替代 structured evidence。

同时禁止：LangGraph、多 Agent、重新引入 PydanticAI、绕过 Harness、复制 Real Pipeline、提前跨入未批准里程碑、开发 Remote MCP；未经用户明确批准不得创建 Tag。

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

*最后更新：2026-09-03 | M5.8—M5.8.5 COMPLETE；M5.9 / M5.10 NOT STARTED；M5 FINAL=false*
