# 09 — 当前上下文交接

> **当前状态入口。** 从根目录 `AGENTS.md` 开始；本文件只回答"现在是什么、下一步做什么"。历史变更见 `CHANGELOG.md` 与 Git。
> **最后更新：** 2026-09-02

## M5.8.4 当前阶段（2026-09-02）

**M5.8.4 — 现有语义链跨语言与通用模型理解优化。** 基线 `m5/rebuild` / `b86662ee00e52e318e09a4c02702cce8feeaab6f`；其 [PowerBIAgent Validation](https://github.com/Strange-Men/PowerBIAgent/actions/runs/33351533445) 已核验 completed/success，M5.8.3 COMPLETE。

当前已完成修改前全后端 A–E 复核、ADR-015/spec、跨语言 failure reproducer、实现、全部本地门禁、Real 与用户人工浏览器验收。主开发提交 `41b6e0b084ac5cbad3b76eb37fa15dd3b89c46a4` 的首次 CI [#33455159267](https://github.com/Strange-Men/PowerBIAgent/actions/runs/33455159267) 因测试 reference date 漂移失败；测试时钟修复提交 `a9753103de6f19d0c95bd4a944d31ca363057d76` 的 CI [#33457056546](https://github.com/Strange-Men/PowerBIAgent/actions/runs/33457056546) completed/success，M5.8.4 COMPLETE。最终治理提交仍须以自己的新 exact-SHA CI success 作为最新封板证据。M5.9/M5.10 NOT STARTED，M5 FINAL=false。

唯一链为 QuestionRouter → Power BI/MCP SemanticModelSchema → immutable ModelSemanticContext → existing SemanticCatalog → Grounding/bounded linguistic selection → runtime members → StateTransition → CanonicalQueryPlan → deterministic DAX → QueryResult → VerifiedFactSet。Power BI 负责结构/对象，Catalog/Grounding 负责 canonical binding，LLM 只在已有 candidate ID 中解释语言，Presentation localization 只显示。无新模型、Planner、Grounding authority、缓存或 Provider/Report/factual 边界变更。

详细失败记录、测试矩阵、Real/性能与 residual 条件见 [M5.8.4 专项计划](milestones/m5/m5_8_4_cross_language_grounding_plan.md)。多次诊断中的语义误绑、过度澄清与 Provider 长尾均保留，不对失败样本宣称 PASS。

后续复核又修复了空 QueryPlan 草稿降级丢筛选、成员 discovery 接受已知子集、旧 Memory owner 覆盖当前显式双字段三条失败路径。pytest 默认 SQLite 已与 HTML 一并隔离；隔离 backend 2312 PASS / 1 SKIP、Golden 11 PASS / 1 manual skip、Semantic Compatibility 658 PASS。完整双 Provider Real 40/40、canonical/result consistency 20/20、30 个真实业务 witness；补强完整槽位/产物断言后的 extended 8/8、双 PBIX isolation 13/13，均 business/temp residual=0。旧失败批次保留，不回填。独立 performance 12/12，warm mean 8040.29ms、4-way wall 30920.78ms，LLM 长尾明显，不宣称性能提升。用户已人工选择“简易模板”并完成浏览器报表生成验收；原自有残留目录只读 `Test-Path=False`，四类 M5.8.4 受控 temp prefix 均为 0。用户明确要求保留两条 ownership 不明会话，它们不属于 M5.8.4 residual；未删除或修改。M5.8.4 明确自建 validation/temp/browser 资源 residual=0。

2026-09-01 首次 M5.8.4 exact-SHA CI #33455159267 在 Semantic Compatibility 第 5 步发现测试日历漂移：相对月份 API case 使用真实当天日期却固定期待 2026-08。通过现有 `today` 注入点固定测试 reference date 后，`a975310` 的 CI #33457056546 completed/success；生产代码与 Real 证据未变化。2026-09-02 最终治理仅修复 bounded selector role 返回 contract、同步状态文档并升级官方 Actions；push 前远程只读审计确认 `m5/rebuild` 尚未 protected，实际正式 check context 为 `Full Validation (Windows)`。该治理提交取得自己的 exact-SHA success 后，再启用只要求此 check 的最小 branch protection。

最终治理 fresh 本地证据：5 类 role × resolved/ambiguous/unresolved/illegal candidate/invalid structured/provider error 共 30 个 selector 直接回归；targeted cross-language unit/API 162 PASS，生产 Chat unknown/ambiguous ZERO DAX、KEEP/REPLACE、Report→Data 5 PASS。Semantic Compatibility 688 PASS / 111 production files；backend 2342 PASS / 1 SKIP；Golden 11 PASS / 1 manual-real SKIP；frontend 86 PASS，typecheck/lint/build PASS。Repository Safety 342 files、AI Error Ledger 55 entries、Architecture 128 production files、Documentation/Artifact Governance、compileall、diff-check 均 PASS。前端 tests 首次与三项编译门禁并行时发生单个 Vitest worker 启动超时；未改配置或代码，停止并行负载后完整 10 files / 86 tests fresh PASS。

最小 Real 没有重跑完整 5 小时矩阵：Rich PBIX + DeepSeek 空 override focused 4/4（中文总销售额、地区分组、销量 Top1、unknown member clarification/ZERO business DAX）及 extended 8/8（时间/筛选 KEEP、分组 KEEP、指标 REPLACE、unknown 后 Memory 不变、Report→Data→Report），共 19 个真实执行 witness，Provider failures=[]，两轮 business_residual=0、temporary_residual=0。应用从仓库根目录启动并由 Settings 正常加载配置；未读取、打印或修改 `.env`。

## M5.8.3 验收收口（2026-08-31）

启动基线为 `m5/rebuild` / `3b811dec214679bb556d4c96506e5e8f536fc5fc`；原修改完整保留，无 reset/revert/丢弃。M5.8.3 实现与 Real 验收收口，正式 COMPLETE 以 fresh local/residual 和对应提交的 PowerBIAgent Validation completed/success 为条件；当前提交自身 SHA/CI 只记录于最终报告。M5.9/M5.10 NOT STARTED，M5 FINAL=false。

- 正式链：Power BI MCP Runtime Semantic Model（结构 authority）→ immutable ModelSemanticContext（metadata 适配）→ validated optional model override（语言/temporal 补充）→ SemanticCatalog → Grounding → frozen StateTransition/CanonicalQueryPlan → deterministic DAX → QueryResult/VerifiedFactSet。LLM 仅 bounded runtime candidate selector；Memory factual authority 不变。
- 原三个 P0 的断点是删除默认 glossary 时丢失合法语言/日期 binding。订单 alias、默认日期角色、月份 grouping 已迁为 inert profiles，必须经 exact opaque identity + 完整 metadata fingerprint + runtime object validation 显式激活。没有恢复 glossary schema authority、自动 profile 选择或自动写 registry。阶段 D 为 462 PASS，当前 Semantic Compatibility 为 **526 PASS**，扫描 111 个 production 文件，无 benchmark leakage。
- 四种真正不同结构：Retail star、Education snowflake、Operations flat/multi-date、未注册 holdout；同一 builder 和正式 Chat API 的 entity/scalar/grouped/ranking/trend 均通过。它们使用受控 LanguageDraft/RuntimeAdapter，不冒充四份真实 Desktop。六类 schema mutation、stale override、duplicate/relationship ambiguity、unknown ZERO DAX 均为永久 fixture Gate；未写入或修改用户 PBIX。
- 真实 Local MCP 已读取两份 Desktop：可见结构分别为 5 tables/20 columns/4 measures/4 relationships 和 1 table/7 columns/2 measures/0 relationships。hierarchy level 实际属性是 columnName；column expression/key/sort、relationship filtering 等证据进入 context/fingerprint。当前对象 description/display 均为空，未观测到 displayName property；不伪造 AI Instructions/synonyms/linguistic schema/AI Data Schema/annotations 支持。
- 用户已明确允许应用 Pydantic Settings 从项目根目录正常加载 .env；Agent 未查看、打印、修改其内容。实际 Settings 布尔检查确认 Real ready；自有 uvicorn 后端在 localhost:8000 启动并通过正式 HTTP Chat/Memory/API 验收，结束后关闭。此前仅依赖 Process/User/Machine 环境变量得出的“Provider 未配置”结论已撤销，不能再次作为 blocker。
- Rich 原 15 项 Real regression PASS：原 scalar/entity/Top1/bounded trend、minimal clarification 与六类非业务隔离断言保留；member-set/filtered aggregation 在当前成员不足时按原合同澄清、ZERO DAX。完整 Chat 的时间/筛选 KEEP、分组 follow-up、measure REPLACE、unknown member 不改 committed Memory、A→B→A 清空跨模型槽全部 PASS。
- Simple Desktop 没有任何 registry binding：真实 ENTITY_LIST/SCALAR/GROUPED/RANKING 四形态 PASS；缺少 authoritative month metadata 时 TREND 最小澄清、ZERO DAX/Memory。fixture holdout 有明确 month projection，TREND PASS。没有为提高成功率猜日期。
- 双 PBIX 组件审计已验证 13 个文本字段/122 个 runtime members、2 个同名不同成员集合及 6 个 transient single-object overrides。完整成员 Chat A→B→A 进一步证明：A/B 各用自己的真实成员，B 拒绝 A 独有成员且 ZERO DAX/Memory mutation，返回 A 重新验证；3 个成功 turn 的生产 fact_set_id 与从实际 QueryResult 重建的 VerifiedFactSet 完全一致。
- 与 exact baseline 的真实比较为 **17/17 Plan、DAX、QueryResult、VerifiedFactSet 相同**。生产 opaque key 按进程随机 HMAC 不变；手工 harness 只观察原 identity 输入并返回原 key，通过同一 nonce 的身份摘要证明两个进程连接同一 Desktop 后才对齐比较投影。真实行和事实只在内存比较，不输出/提交业务数值。
- 性能观察：有效对比 warm 平均 5742.25→2433.50ms，4-way wall 5848.79→7193.27ms；当前并发尾部主要为 Intent 5750ms/QueryPlan LLM 4750ms。较早一组 warm 为 1812.50→1996.25ms，4-way 当前曾出现 33.64s LLM 长尾，不能隐去或把最好一轮当 SLO。context 独立 build 1.171/0.521ms、catalog 0.261/0.148ms；warm profiler context 低于计时分辨率、catalog 0–16ms，session reuse=1。未发现 context 重建导致明显退化；没有更改 M5.8.1 worker/TTL/cache/singleflight/concurrency，也没有新增 cache 或开展 M5.9 压测。
- Real 集成发现并修复：长限定字段名丢失 GROUPED cue；Router 已知只读 shape 的无效 Intent weak draft 没有进入 Grounding；完整 Measure 名中的 Column 子串造成假筛选歧义。分别有 failure reproducer、正反例及 fresh Semantic Compatibility。Router 仅修正有界 grouped 名称长度，六 routes/八 shapes/slot authority 不变；不是声称 Router 文件零修改。另修复只读 ownership probe 未 close SQLite 导致 Windows 文件占用，不改业务持久化语义。
- cleanup 收口后的最终 fresh 本地：cleanup **15 PASS**；backend **2168 PASS / 1 SKIP**（200.91s，完整无 .env 副本内运行）；Golden **11 PASS / 1 manual-real SKIP**；frontend **86 PASS**（10 files），typecheck/lint/build PASS；Repository Safety **337 files**、Architecture **128 production files**、Error Ledger **45 entries**、Artifact Governance PASS。Documentation Governance、compileall、git diff --check 同步后均 PASS。
- residual：此前两份明确目录均已由用户清理并 Test-Path=False；本轮最终只读扫描四种受控 prefix 均没有残留；完整验证副本在 finally 中清理并实际确认 temporary_residual=0。标准受控 mkdtemp/finally + ownership marker/exact path/目录身份校验已统一验收临时目录，15 项永久回归通过；正常/异常/取消均尝试清理。拒绝清理只报告路径、原因和真实 residual，不能伪报零、误删他人目录或反复要求常规手工删除。模拟残留由外层 fixture 自动回收。
- 发布流程：本次仅完善 scripts/test temp lifecycle，不改冻结业务 authority；运行 fresh 全量 Gate 后白名单 staging，使用用户指定标题 M5.8.3_MCP驱动通用模型语义适配最终收口，push m5/rebuild，并只接受新 exact SHA 的 PowerBIAgent Validation completed/success。旧基线 CI 33163481580 success 不能替代。
- 规范：`docs/specs/model_semantic_context.md`；验收计划：`docs/milestones/m5/m5_8_3_model_semantic_context_plan.md`。Provider、Report renderer/template、DAX/QueryResult/VerifiedFactSet/Memory authority 保持不变；未引入 Redis/RAG/Ontology/Vector DB，M5 FINAL=false。

## 当前阶段

**M5.8.3 — MCP驱动通用模型语义适配。** 实现、Real 验收和 temp lifecycle 收口；只有 fresh local/residual 与对应提交 CI success 均成立才为 COMPLETE。M5.8/M5.8.1/M5.8.2 authority 冻结，M5.9/M5.10 NOT STARTED，M5 FINAL=false。

| 子版本 | 内容 | 状态 |
|--------|------|------|
| M4.2 series | 会话/报表恢复与 metadata authority 最终收口 | ✅ FINAL PASS |
| M4.3 | Conversation History / Search API | ✅ 完成 |
| **M4.4** | **Restart / Crash Acceptance & M4 Final Closure** | **✅ M4 FINAL PASS** |
| **M4.4.1** | **Memory corruption fail-closed + README/document closure** | **✅ FINAL PASS** |
| **M4.4.2** | **M0–M4 truth / persistence boundary final closure** | **✅ FINAL PASS** |
| **M5.0** | **前端设计与契约固化** | **✅ 已完成** |
| **M5.1** | **React 前端实现与核心联调** | **✅ 已完成** |
| **M5.2** | **真实业务链路与前端逻辑收口** | **✅ 已完成** |
| **M5.2.1** | **模型能力边界与真实模式说明收口** | **✅ 已完成** |
| **M5.3** | **结构化结果与前端最终收口** | **✅ 已完成** |
| **M5.3.1** | **多 PBIX 绑定与展示事实边界最终加固** | **✅ 已完成** |
| **M5.3.2** | **Local MCP 多模型选择与协议稳定性加固** | **✅ 已完成** |
| **M5.3.3** | **多轮语义、会话资源生命周期与 Artifact Governance** | **✅ 已完成** |
| **M5.4** | **多会话并发、用户设置与资源管理最终收口** | **✅ 已完成** |
| **M5.4.1** | **Settings Hub、全量历史资源分页与 test-owned cleanup** | **✅ 已完成** |
| **M5.4.2** | **M5 重建基线、实验线审计保留、分阶段路线与 Generalization Gate** | **✅ COMPLETE** |
| **M5.5** | **Semantic correctness 与 capability boundary** | **✅ COMPLETE** |
| **M5.6** | **Presentation/Localization/Resource UX truth** | **✅ COMPLETE** |
| **M5.7** | **简易报表视觉 + Report Template Required + 人工视觉验收** | **✅ COMPLETE** |
| **M5.7.1** | **统一语义可靠性、回归防火墙与高强度问答验收** | **✅ COMPLETE** |
| **M5.7.2** | **Report Template Gate 前移、Template/Renderer Registry、前端模板选择 UX、简易模板视觉与信息架构最终修复** | **✅ COMPLETE** |
| **M5.8** | **多 LLM Provider 抽象 + DeepSeek/Kimi 最小双模型** | **✅ COMPLETE** |
| **M5.8.1** | **前置性能加速与本地 MCP 会话复用** | **✅ COMPLETE** |
| **M5.8.2** | **通用自然语言路由与查询形态收口** | **✅ COMPLETE** |
| **M5.8.3** | **MCP-driven ModelSemanticContext 与任意 PBIX 通用语义适配** | **验收收口；对应提交 CI success 后 COMPLETE** |
| **M5.9** | **完整 MCP performance/resilience、并发压力与故障恢复** | **⏳ NOT STARTED** |
| **M5.10** | **固定专业销售报表模板与两模板选择** | **⏳ NOT STARTED** |

### M5.7 completed contract

- 当前分支/启动 SHA：`m5/rebuild` / `4d4881735a5d87f9dc6e1cb42501559deaf38f6d`；启动时远端一致、工作区干净且无 merge/rebase/cherry-pick。
- 当前唯一目标：把既有 `sales_report.html` 固化为“简易模板”，完成响应式可读性优化与 `Report Template Required` Gate。
- 任何 report intent/request 必须显式携带 registry-valid `report_template_key`；missing/invalid/stale template 必须 clarification/template-required，且 ZERO ReportData assembly、ZERO ReportSpec、ZERO renderer、ZERO HTML artifact。禁止默认 `sales_report`、自动猜测或 fallback 第一项。
- 前端 selector 只提供模板 choice，不决定用户 intent，不增加 Chat/Report 模式切换。M5.7 不修改 M5.5 Grounding/StateTransition/Deterministic DAX/VerifiedFactSet authority、M5.6 Presentation authority、MCP、LLM Provider 或 resource lifecycle。
- 后续路线固定：M5.8 只做 OpenAI-compatible Provider、LLMModelProfile、DeepSeek/Kimi-K2.6 与 request/conversation-scoped model selection；M5.9 只做 MCP profiling/session reuse/cache/concurrency/queue/restart/fault/soak；M5.10 只做固定专业销售模板与两模板选择。只有 M5.10 全部门禁完成后才允许声明 M5 FINAL。

### M5.5 current contract

- 当前分支/启动 SHA：`m5/rebuild` / `1e606aaa11cca27e9ea63dc0318b0372b4f91bf7`；远端启动时一致，工作区干净。
- 唯一目标：Semantic correctness、capability boundary、multi-turn inheritance、runtime object/member authority、ranking/TopN 与 temporal semantic intent。
- 核心 Gate：explicit unresolved semantic requirement → clarification/no-match → ZERO DAX、ZERO QueryResult、ZERO Memory commit；当前 no-match/ambiguity 不得被旧 Memory 掩盖。
- authority 保持 TurnPipeline、ToolGateway → PowerBIAdapter、Deterministic DAX、QueryResult、VerifiedFactSet、Memory 与 stale-model fail-closed 不变。
- Generalization Gate 覆盖 Sales/Retail、Education、Inventory/Operations、未知 holdout 和 schema mutation；生产代码不得加入 sales-specific object/member hardcode。
- M5.6 action menu clipping/Settings nested-scroll 修复与 M5.10 专业销售模板各归所属阶段；M5.5 不实现 Localization、Presentation redesign、Report Visual、MCP performance/cache/session worker、Remote MCP。

### M5.6 completed contract

- 用户已在 `m5/rebuild` 的 M5.5 commit `0aa54ba5b4842f0b5faf161f6dcb3969a7db13e9` 上批准 M5.6。只允许 Presentation、Localization 与 Resource UX truth；M5.5 semantic authority、DAX、MCP、report renderer 与当时后续里程碑均冻结。
- display binding key 至少为 model/object/type/locale/schema identity；解析优先级为 metadata、model glossary、persisted registry、bounded existing-object translation、safe fallback。canonical identity/value/provenance 不变，unknown object 不可创建。
- scalar 只显示自然语言；grouped/trend 的 Answer 只总结 VerifiedFactSet 中的关键发现，完整明细留给 table/chart；raw ISO timestamp 不得进入可见文本。
- Settings/Recent report 共用正式 resource source；conversation 按 updated/created/stable ID 全降序。failed conversation 必须持久化且可 rename/archive/restore/delete，不因请求错误成为 ghost session。
- conversation/report 共用 Portal floating menu；Settings 使用 fixed header/navigation/content scroll/resource toolbar/list scroll。Layout Gate 覆盖首中末、滚动三位置、20/50/100 resources、规定 viewport 与 100%/125% zoom。
- P1—P12 已顺序通过；最终文档、fresh full gates、residual=0、白名单 commit 与 push 均完成。
- Rich PBIX `每个月销售额趋势` 由 model-scoped glossary 的 `YearMonth` temporal binding 解析，DAX 正常执行；可见 Answer 只总结峰值/回落/回升，table 为中文月份/金额，line chart 与可见文本均无 raw ISO timestamp。
- Fresh final gates：backend `1849 passed, 1 skipped`；frontend typecheck/lint/build PASS、Vitest `79 passed`；Golden `11 passed, 1 manual-real skipped`；Architecture `120`、Repository Safety `302`、Error Ledger `34`、Documentation/Artifact Governance、compileall、Alembic fresh/head-idempotent 与 `git diff --check` PASS。P11 automation-owned conversation teardown 后 residual=0。

### M5.4.2 completed contract

- 当前分支：`m5/rebuild`；基线：M5.4.1 `cab40b076f054a3ebdab0bf6d2b0354f4b2d49db`。
- 旧实验线 `m5/frontend`、`a197db3`（原 M5.5）与 `6d1620a`（原 M5.5.1）保留为研究/失败经验/审计记录；不删除、不重写、不 revert、不整体 cherry-pick。旧 PASS 不能替代新线 Real Acceptance。
- 本轮只允许 Git 基线和文档/治理变化；不得修改 `backend/app/**`、`frontend/src/**`、测试、schema 或 migration，不得开始新版 M5.5。
- M5.4.1 的 Agent-first、Local MCP readonly、多 PBIX opaque exact binding/stale fail closed、事实链、多轮基础语义、conversation-scoped concurrency、Settings 分页、resource lifecycle、ownership/residual=0 全部保留。
- 后续严格按 M5.5 Semantic、M5.6 Presentation/Localization/Resource UX、M5.7 简易报表视觉/模板必选、M5.8 LLM Provider/双模型、M5.9 MCP performance/resilience、M5.10 专业销售模板分域开发；只有 M5.10 全部门禁完成后才允许声明 M5 FINAL。
- 长期问题与验收合同见 `docs/specs/13_m5_generalization_and_acceptance_contract.md`。其中 explicit unresolved semantic requirement 必须 clarification/no-match 且 ZERO DAX；Generalization Gate 至少覆盖 Sales/Retail、Education、Inventory/Operations 和最终未知模型 holdout。
- Fresh governance：Documentation Governance、Repository Safety（296 files）、Error Ledger（30 entries）、Artifact Governance 与 `git diff --check` PASS；无功能测试要求，因为本轮未修改业务逻辑。

### M5.4.1 final implementation and evidence

- 根因：Settings 复用 Sidebar `limit=12` 的 recent 第一页；report 再对该 conversation 子集聚合并截断到 8；旧选择逻辑截断到 20。SQLite server-default 秒级时间与带微秒 cursor 的文本比较还会让同秒资源重复第一页。
- Sidebar Recent 继续 bounded/轻量。Settings 使用独立 query state 与 namespace-scoped cursor pagination，完整覆盖 active/archived conversation 及 active/archived report，并显示 total/loaded/selected/has-more。
- “全选当前已加载”只选择当前已加载行；不得让用户误以为第一页等于全部。全部历史至少可持续加载并任意多选。
- 选择与执行解耦：一次确认可超过 20 项，前端按最多 20 项一组调用正式单资源 API，逐项精确汇总 partial failure；不新增 `DELETE ALL`。
- report rename/archive/restore/delete 继续遵守 presentation title、filesystem HTML、factual metadata、namespace 与 tombstone authority。
- Codex/pytest/browser/Real/MCP/report 自动化资源必须显式登记 test ownership，在 `finally` 中通过正式 API/repository cleanup 并验证 conversation/report/HTML/SQLite namespace/delete intent/orphan residual=0；任一残留 Gate FAIL。
- 历史清理只处理有 ownership metadata、known test namespace/ID、fixture 或 report linkage 证据的资源；无法确认 ownership 的现有资源保留。
- 本轮不修改 TurnPipeline factual semantics、DAX、Memory、VerifiedFactSet 或 ReportSpec authority；M5.5 Deferred。
- 正式实现：独立 conversation/report active/archived cursor API、`total_count`、SQLite `julianday + stable ID` keyset、20 项按需加载、任意多选和最多 20 项执行 wave；migration `b7c9d2e4f610`。
- Real Browser：25 conversations 从 20/25 加载到 25/25，Sidebar 仍为 12；25 项一次确认以 20+5 archive/restore。10 reports 的 rename/archive/restore/delete/tombstone/restart 通过。
- automation ownership registry、finally cleanup CLI 与 Artifact Governance exact SQLite probe 已启用；本轮 teardown 后 conversation/report/HTML/SQLite/delete-intent residual=0，未知 ownership 数据未删除。
- Fresh gates：backend `1797 passed, 1 skipped`；Vitest `69 passed` 且 typecheck/lint/build PASS；Golden `11 passed, 1 manual-real skipped`；Architecture `118`、Repository Safety `295`、Error Ledger `27`、Documentation/Artifact Governance 与 `git diff --check` PASS。

### M5.4 root-cause baseline（代码修改前）

- `usePowerBIAgent()` 仅维护一组全局 `messages / activeConversationId / sending / loadingConversation / error`，把“当前展示哪个会话”与“哪个会话正在执行”错误合并。
- 新聊天在后端返回 conversation ID 前没有稳定 local identity，因此无法立即出现于 Sidebar，也无法让 A pending 时 B/C 独立发送。
- M5.3.3 已为 history navigation 建立 abort/generation/active identity 保护，但 business chat 仍绑全局 sending/messages，不能表达不同 conversation 同时 pending。
- 当前 Sidebar 使用长 recent list，用户卡片纯展示；批量 conversation/archive/report 管理、report rename 和 deleted tombstone 尚未实现。

### M5.4 approved implementation contract

- 使用 `conversation_id → ConversationSession` 隔离 messages/pending/sending/history/error/status；active ID 只决定当前可见 session。
- 新会话首次发送由前端生成合法 UUID，同一 ID 直接传给 Chat API；Sidebar 立即合并 local pending row。
- 不同 conversation 允许并发，同 conversation 保持串行。history fetch 可取消，business chat 归属 conversation，切窗不取消也不自动回跳。
- 用户卡片打开设置/已归档/资源管理；Sidebar recent/report 独立滚动与折叠，批量 checkbox 只在资源面板。
- 批量操作最多 20 项，协调正式单资源 API 并呈现 partial failure；不增 `DELETE ALL`，不绕过 durable delete，archive ≠ delete。
- report delete 保留 presentation tombstone；report `display_title` 只是 presentation metadata，report_id/HTML/content_hash/ReportSpec/VerifiedFactSet 不变。LLM/ToolGateway 无 rename/delete 权限。
- M5.5 语言理解、Localization Registry、单指标展示、HTML 视觉与性能继续 Deferred。

### M5.4 — 最终实现与验收

- `usePowerBIAgent()` 以 `conversation_id → ConversationSession` 保存 messages、pending request、sending、history、error 和 status；active ID 仅选择可见会话。首次发送使用前端 UUID 作为正式 Chat identity，pending row 无需等待后端。
- business chat 不携带 navigation Abort signal，按 owning conversation 回写；不同 conversation 可同时运行，同 conversation 由 running guard 串行。history 继续使用 AbortController/generation/active identity，后台完成不切换当前窗口。
- 用户卡片提供设置/已归档/资源管理入口；最近对话与报表可折叠，recent 独立滚动。资源面板最多选择 20 项，通过单资源 API 协调批量删除/恢复，并逐项保留 partial failure。
- `report_presentations` 与 migration `a4f6b8c2d190` 保存 `display_title`/availability。PATCH 只改 presentation title；delete 仍清理 HTML/factual metadata 并保留 transcript tombstone。conversation delete 会清理同 namespace presentation row；接口不注册 ToolGateway。
- Rich PBIX Real A/B/C 并发结果分别为总销售额 `6,943,997.51`、四区域销售表、总销量 `3,065`；pending/loading/result 均隔离且无自动跳窗。归档恢复、report rename、delete 后 reload/history tombstone 无 view/download 均通过。
- 本轮 9 个 Real acceptance conversation 与关联 report 通过正式单资源 API 精确清理。一个此前无 DB ownership 的 `test01.html` 未删除，已可恢复归档到 `local_state/archive/m54_preexisting_orphan_20260824/`，Artifact Governance PASS。
- Fresh evidence：backend `1790 passed, 1 skipped`；frontend typecheck/lint/build PASS，Vitest `61 passed`；Golden `11 passed, 1 manual-real skipped`；Architecture `117`、Repository Safety `290`、Error Ledger `25`、Documentation Governance、Artifact Governance、`git diff --check` PASS。
- M0–M5 factual/Memory/VerifiedFactSet/Report authority 未改变；M5.5 未开始；不合并 main，不创建 Tag。

### M5.3.3 root-cause baseline（代码修改前）

- 真实浏览器 conversation `2704941c-…` 的五轮证据显示：前五轮全部 `completed` 且 `memory_commit=true`。第 2 轮 `2025年5月销售额多少` 的 committed `time_range` 仍为 2026-08 current_month；第 3 轮虽正确解析 Region/Top3/desc，仍 KEEP 该时间；预测与 PBIX Measure 修改又分别把同一旧 plan 提交为 Memory v4/v5。
- `TimeGrounder` 仅识别本月/今年/去年/最近数字月/两个 ISO date，无法消费 LLM 的结构化当前时间语义；未识别的当前表达被当成 NOT_MENTIONED。
- `StateTransitionService` 对同 conversation 的所有未指定 slot 默认 KEEP，没有 fresh/follow-up/replace 决策，因此自包含新问题机械继承旧 time/filter/dimension/sort/top_n。
- Intent 与 QueryPlan Prompt 都注入全部 committed slot，LLM 可能重复旧槽；Grounding 已有部分 current-literal 防腐，但无法纠正“当前时间未识别 + 默认全量继承”的组合。
- `should_defer_unsupported_to_grounding()` 明确以 `committed is not None` / pending 为放行条件，导致 LLM 已识别 unsupported 的预测/写请求仍进入 data pipeline。
- 前端 `openConversation()` 在 history 完成后才设置 active ID，且无 AbortController/generation/identity re-check；慢 A response 可在用户已切 B/new/archive/delete 后覆盖 messages/title/report attachment。
- 后端 report history 已按 `(source_mode, conversation_id)` 查询，未发现跨 namespace predicate；A/B 串窗当前证据指向前端 stale response/state lifecycle。

正式实现契约见 `docs/specs/12_conversation_memory_and_resource_lifecycle_contract.md`。

### M5.3.3 — 最终实现与验收

- Intent 新增 bounded `turn_relation` 与 `TimeIntentDraft`；deterministic resolver 处理绝对月、去年五月、上个月、季度、最近月/半年与受限范围。runtime schema/glossary/members 和 validators 继续拥有 canonical authority。
- `TurnInheritancePolicy` 将 fresh/follow-up/replace 分离：自包含新问题清除旧 time/filter/dimension/sort/top_n；明确追问或替换只继承兼容省略项；证据不足 clarification；semantic model 切换清空旧模型语义上下文。
- readonly unsupported preflight 在 LLM/Memory/Grounding/DAX 前拒绝预测、PBIX/Measure 写操作、删除数据和任意代码；terminal Snapshot 保留审计，Memory 不提交。
- archive 从 recent 隐藏但保留 conversation/history/report/HTML，并通过 archived/restore API 恢复；独立 `DELETE /api/reports/{report_id}` 使用 durable report delete intent 精确清理 metadata/cache/HTML，conversation 保留，且不注册 ToolGateway。
- history 只恢复 exact `(source_mode, conversation_id, request_id, report_id)` ownership；前端使用 AbortController + generation + active ID + response ID 四重检查，open/new/delete/archive/model switch 使旧 history 失效。
- local_state 固定四目录；Artifact Governance 检查 ownership residual、cleanup failure/pending、orphan/mismatch、unauthorized entry 与 source-tree runtime artifact。pytest 默认 report root 改为 per-test 临时 ownership，teardown 后验证清理。
- Rich PBIX Real 八轮：本月、2025-05、Top3 Region、华南 follow-up、去年 replace、预测 unsupported、PBIX 修改 unsupported、report generation 全部符合契约；archive/restore、独立 report delete（对话保留）、再生成后 conversation cascade delete、A/B 快速切换均通过。
- Fresh 验证：backend full `1789 passed, 1 skipped`；frontend typecheck/lint/build PASS，Vitest `49 passed`；Golden `11 passed, 1 manual-real skipped`；Architecture `117`、Repository Safety `287`、Error Ledger `25`、Documentation Governance、Artifact Governance 与 `git diff --check` PASS。

### M5.3.2 — Local MCP 多模型选择与协议稳定性加固

- `PowerBILocalMCPClient` 将 beta.12 `ListLocalInstances` raw payload 严格转换为内部 typed identity；后端使用 PID、local data source 与 start time 的 canonical identity 经进程内密钥 HMAC-SHA-256 生成 `local_desktop:<opaque-id>`。display name 不参与 identity；API/前端不暴露 PID、端口、connection string、raw fingerprint 或 MCP payload。
- discovery 返回所有当前 Desktop option。每个 option 的 compatibility 都执行精确绑定 probe；schema/member/DAX 的每个新 stdio session 都重新 `ListLocalInstances → opaque key 唯一匹配 → Connect → session connectionName`，不存在 `instances[0]`、display-name guess 或其他 PBIX fallback。
- Desktop 重启/关闭、后端进程重启或 identity 变化使旧 key stale；schema/member/DAX deterministic fail closed。前端刷新目录、清空失效选择并要求重选，不持久化 instance registry，不自动切换剩余模型；重复 display name 只显示“实例 1/2”。
- 固定 `@microsoft/powerbi-modeling-mcp@0.5.0-beta.12`。只读 capability probe 覆盖 server startup、protocol、required tools、ListLocalInstances、Connect、schema List/Get，以及 `EVALUATE ROW("__pbiagent_probe", 1)` 的列、一行和值；结果不进入 Memory、Snapshot 或业务 Trace。
- DAX wire 请求使用 `request.max_rows + 1` sentinel，并验证实际 columns/rows/rowCount 与 wire limit。显式 truncation/limit metadata 映射到 `QueryResult.truncated`；无完整性证明且触及上限时保守 truncated，不做任意 DAX 分页，VerifiedFactSet 既有 truncated 语义不变。
- `sales_report` 的 registry 逻辑 binding 与 opaque instance resource identity 显式分离；TemplateContract、deterministic queries、VerifiedFactSet、renderer 与 M0–M4 factual/Memory/Report authority 未改变。无 migration，Remote MCP 继续 Deferred。
- Real Smoke：同时打开 `PowerBIAgent_M3_Rich_Test.pbix` 与 `PowerBIAgent_M3_Test.pbix`，safe API 同时返回两个 unique/selectable option；两者 probe/schema/DAX 均成功，模型专属查询证明不串实例；浏览器可分别单选，Rich 问答、表格/柱状图与 HTML 报表成功。关闭 Rich 时 Desktop 显示未保存更改确认且检测到用户输入，因此未强制丢弃本地状态；live stale-shaped key 与 fake disappearance 回归均验证下一请求 fail closed。
- Fresh 验证：backend full `1760 passed, 1 skipped`；frontend typecheck/lint/build PASS，Vitest `39 passed`；Golden `11 passed, 1 manual-real skipped`；Architecture `116`、Repository Safety `280`、Error Ledger `25` PASS。Settings.version 为 M5.3.2；frontend version 为 5.3.2。

### M5.3.1 — 多 PBIX 绑定与展示事实边界最终加固

- 根因：Local MCP discovery、schema、member lookup 与 DAX 分别建立 stdio session，每次都重新执行 `ListLocalInstances → instances[0] → Connect`。多个 Desktop 同时打开时，不同阶段可能连接不同 PBIX，形成“数据真实但来源模型错误”的 P0 风险。
- Local MVP 采用最小唯一实例 contract：每个 session 的 `ListLocalInstances` 必须恰好返回一个 Desktop 实例；0 个保持 `powerbi_desktop_not_connected`，多个在 `Connect` 前 fail closed 为 `powerbi_multiple_desktop_instances`。不按顺序或 display name 猜测，不新增 instance registry。
- discovery/schema/member/DAX 共用同一检查；单实例 Rich 路径不变。前端对多实例显示自然语言提示并禁止发送，不暴露连接 identity 或 MCP raw payload。
- stdio 关闭可将受控 Desktop 错误与 cleanup 错误组合为 `ExceptionGroup`；分类器现会保留 `DESKTOP_NOT_FOUND` / `DESKTOP_CONNECTION` 中的安全错误码，避免多实例被上层归一为通用 discovery unavailable。
- `PresentationDataset` 不再复制完整 QueryResult；只按 scalar/grouped/ranking/min/max VerifiedFact `source_fields` 保持 QueryResult 原顺序投影 columns/rows。metric/table/chart 全部引用该 verified dataset，额外列不进入 presentation，row/column shape mismatch 继续 fail closed。
- 正式 PRD 已同步 M5.3 presentation、transcript/title/rename/delete、metric/table/bar/line/report attachment 与 Rich PBIX acceptance；comparison/YoY/arbitrary trend、Remote MCP、多租户/RLS 等仍 unsupported/deferred。
- Settings.version 为 M5.3.1；frontend version 为 5.3.1。无 migration，无 M0–M4 authority 变化，无后续里程碑扩展。
- Fresh 验证：backend focused `98 passed`，backend full `1743 passed, 1 skipped`；frontend typecheck/lint/build PASS，Vitest `34 passed`；Golden `11 passed, 1 manual-real skipped`；Architecture `116`、Repository Safety `280`、Error Ledger `25`、Documentation Governance 与 `git diff --check` PASS。
- Real Smoke：Rich 单实例 discovery 为 compatible/selectable，简单问答、表格、报表均成功；同时打开第二个 PBIX 后明确返回 `powerbi_multiple_desktop_instances`，关闭后 Rich 立即恢复。未修改或保存 PBIX。

### M5.3 — 结构化结果与前端最终收口

- 新增安全启动诊断：严格 `.env` 行格式只允许 `KEY=value`、注释和空行；CLI 与 `/health` 只输出模式、readonly、工具预算及 DeepSeek“是否配置”，不输出值或 Secret。
- discovery 在 ToolGateway 只读 schema 路径上执行当前 Semantic Catalog/glossary 最小兼容性构建；完整 fingerprint 仅标记 `schema_drift`，不单独阻断模型。只有缺少必需业务对象或对象类型冲突才返回 `incompatible` 并由 UI 禁用发送，不暴露 schema/hash/DAX。
- 新增 presentation-only transcript/title：terminal Snapshot 保存本轮 `user_message` 与 `presentation`；conversation 首个有效问题生成默认标题，支持 namespace-scoped PATCH 重命名。两者不进入 WorkMemory、Grounding、QueryPlan 或 VerifiedFactSet。
- 新增 `PresentationEnvelope`：每个 QueryResult 只保存一份 dataset，包含 verified fact linkage；动态 block 支持 text、metric、table、bar/line chart 与 report attachment，所有数据块只通过 `data_reference` 和字段名引用 dataset。
- Sidebar 支持搜索、完整历史恢复、重命名、归档、删除；报表按 conversation 管理，DELETE 继续复用 M4 durable delete intent 清理关联 managed HTML，没有独立 report delete API。
- 前端完成白色主区/浅灰 Sidebar、内容宽度、固定 Composer、折叠、菜单定位、表格横向滚动、图表尺寸、报表附件、hover/focus/loading/disabled/error/empty，以及 desktop/medium/small responsive 和 ESC/focus-visible/aria/keyboard 基础 accessibility。
- 已在浏览器验证 Rich PBIX Real `local_desktop` discovery；fingerprint drift 下保持 connected/compatible/selectable。六轮问答完成时间与区域筛选继承，真实表格与 HTML 报表生成、查看/下载、recent/history/search 均通过；测试 conversation 与关联 managed HTML 已经正式 DELETE API 精确清理。
- Alembic head 更新为 `d3b7f9a1c524`，仅增加 nullable conversation `title`；无 M0–M4 factual schema/authority 变化。
- Fresh affected backend regression：`335 passed`；frontend typecheck/lint/build PASS，Vitest `31 passed`；Golden `11 passed, 1 manual-real skipped`；Architecture `116`、Repository Safety `279`、Error Ledger `25`、Documentation Governance 与 `git diff --check` PASS。

### M5.2.1 — 模型能力边界与真实模式说明收口

- 根因：Mock discovery 直接遍历 `mock_schema.json` 的全部 fixture，并统一标记 `available=true/connected=true`；`SemanticModelOption` 与前端消费语义实际是可选择模型，因此 `mock_satisfaction_model` 被错误提升为正式业务能力。
- 修复：`MockPowerBIAdapter` 使用最小显式白名单，只向 discovery 返回 `mock_sales_model`。`mock_satisfaction_model` fixture 与直接 schema 读取能力保留，继续服务聚焦测试，但不进入前端目录。
- Real Local MCP discovery 未改，仍返回单一 `local_desktop_model` 安全选项；未新增 `selectable/supported` 字段，未扩大 API 或前端类型复杂度。
- 根 README 在快速开始顶部增加“本地 Power BI 真实模式启动”，明确默认 Mock、Real `.env` 键、启动顺序、SQLite 前提与 `/health`、`/api/v1/semantic-models` 检查；根 README 和 `frontend/README.md` 的普通标题与叙述统一为中文。
- Fresh 验证：discovery 聚焦 `5 passed`；PowerBI/semantic-models/health 受影响回归 `86 passed`；Mock pipeline `41 passed`；前端 Vitest `21 passed`，lint/typecheck/build 全部通过；Architecture Gate `111`、Repository Safety `270`、Error Ledger `25` 与 Documentation Governance 通过。
- 无 M5.3 视觉 polish，无 DB schema/migration，无 M0–M4 核心链重构；未创建 Tag。

### M5.2 — 完成状态与固化边界

- 数据模型不是前端固定“Power BI 销售数据”别名。浏览器不能读取 `.pbix`；后端通过 Local MCP / 当前 Desktop 实例发现和连接，前端只展示只读 discovery endpoint 返回的 safe catalog。
- `local_desktop_model` 仅保留为 M2 封板兼容的后端内部执行 identity，不再作为前端静态产品目录；当前 Local Adapter 一次只稳定连接一个模型时，UI 明确标记“当前已连接模型”。
- M5.2 当时将 `report_template_key` 作为 request-level 可选 override，并允许 report intent 自动选择默认 `sales_report`；该历史行为已由 M5.7 Report Template Required 合同 supersede。
- M5.2 负责 Real、Desktop discovery、SQLite conversation 配置、runtime/source namespace、真实多轮与 report、最小错误分类和结构化表格/图表契约审计。
- M5.3 才负责尺寸/间距、responsive、accessibility、loading/error/empty polish、表格/图表视觉和最终浏览器视觉收口。

### M5.2 实现与 Real acceptance

- 新增 `GET /api/v1/semantic-models`：API → `SemanticModelDiscoveryService` → read-only `ToolGateway` → `PowerBIAdapter` → Local MCP。响应只有 stable key、display name、source/type、availability/connected 与 runtime namespace，不返回端口、process ID、connection string、MCP raw payload、DAX 或 schema。
- 当前 Local execution contract 一次只选择并验证一个打开中的 Desktop 模型；前端动态加载 safe catalog，无模型时禁止发送并显示 Desktop/模型 empty state，不再伪造销售模型。
- M5.2 当时由 `TemplateCatalog` 为 `report_generation` 选择 registry-owned 默认 `sales_report`；该历史行为已由 M5.7 显式模板必选 Gate supersede，普通 Chat 仍不受影响。
- Real 启动使用 `LLM_MODE=deepseek`、`POWERBI_MODE=local_mcp`、`PERSISTENCE_BACKEND=sqlite`、`MAX_TOOL_CALLS=8`。本地旧值 `MAX_TOOL_CALLS=3` 会在 full report 的第三个 DAX 前被 TurnController 拒绝；独立四查询均成功，改回正式预算后 generic report 执行 schema + 4 DAX + render 并 completed。
- 当前 Desktop schema 与 model-scoped glossary 的旧 fingerprint 不一致；只读兼容性检查确认所有 glossary object/type/visibility 仍匹配后，仅更新 fingerprint，未放宽 Semantic Catalog authority。
- Fresh Real 7-turn conversation 使用同一 conversation_id、不同 request_id，类别/筛选/指标切换/产品维度/Top2/未指定模板的 generic report 全部 `completed`、`memory_commit=true`、`source_mode=real`；report 自动选择 `sales_report`。recent/search/history(7 turns)/conversation report/view/download 均通过，report view/download 同源；dispose/restart 后 history/report/view 可恢复。
- 实际浏览器确认 Desktop display name、模板 catalog（无“不使用模板”）、recent/search/history、用户可理解错误消息与 ReportArtifact 附件。未强制关闭用户正在运行的 Desktop；Desktop absent 采用 Adapter/API/frontend safe fault-injection 回归，避免丢失未保存 PBIX。
- Chat/History 仍没有 QueryResult columns/rows、独立 metrics 或 ChartSpec。本轮不新增高风险事实 response adapter，不从 answer/audit 反解析；结构化表格/图表契约明确 defer 至 M5.3 前。
- Fresh gates：frontend typecheck/lint/build PASS、Vitest `21 passed`；backend `1708 passed, 1 skipped`；Golden `11 passed, 1 manual-real skipped`；Architecture Gate `111`、Repository Safety `270`、Error Ledger `25`、Documentation Governance 与 `git diff --check` PASS。

### M5.2 启动故障基线

- 以仓库当前默认启动配置复现：`/health` 为 Mock+Mock ready；conversation/search 因 `persistence_backend=memory` 返回 `503 conversation_history_requires_sqlite`。数据库文件存在不等于 SQLite provider 已启用。
- 同一配置下 Chat HTTP 200 但业务 `terminal_state=tool_failed`、`error_type=ToolPolicyDeniedError`、`memory_commit=false`；根因是前端默认 Real/`local_desktop_model` 与后端 Mock/`mock_sales_model` 不一致。HTTP 200 不是业务成功。
- M5.2 已让前端 runtime/model 来自后端 discovery，并完成 SQLite + DeepSeek + Local MCP 的显式 Real acceptance。

### M5.1 — React 前端实现与核心联调

- `frontend/` 已创建 React 19 + Vite 8 + TypeScript 6 工程，使用 hooks、普通 CSS、lucide-react、Vitest 与 Testing Library；无重型 Dashboard 框架、路由器或全局状态库。
- 已实现 AppShell、真实折叠 Sidebar、新聊天欢迎态、已有对话态、稳定底部 Composer、"+"数据模型/报表模板菜单与 DeepSeek-only 单选卡片。
- Chat adapter 发送 `conversation_id` / `request_id` / `semantic_model_key` / `report_template_key`，动态渲染 answer、clarification、unsupported、error、empty 与真实 ReportArtifact；不展示 trace/tool/audit/Memory/DAX/usage。
- recent/search/history/reports 已接现有 SQLite API。Conversation 请求显式 `runtime_mode`，report 请求显式 `source_mode`；History 只恢复 persisted structured result，并在 UI 明示不是逐字 transcript。
- 项目卡片与用户账户保持纯展示。M5.1 当时没有 discovery endpoint；该限制已由 M5.2 的只读 semantic-model discovery supersede，模板仍在 `src/config.ts` 集中登记。
- 报表查看/下载只使用与 `report_id` 严格一致的后端 canonical reference；无 report resource 时不显示附件。
- 最小契约缺口：Chat/History 不暴露 QueryResult `columns/rows`、独立 metrics 或 ChartSpec，`execution_audit` 也没有可消费 rows。M5.1 不修改 M4 Snapshot/Persistence，不从 answer/audit 推导事实，因此不渲染假表格/图表。
- Fresh gates：frontend typecheck/lint/build PASS，Vitest `13 passed`；Chrome 1600×1000 实际欢迎态检查 PASS；backend `1700 passed, 1 skipped`；Golden `11 passed, 1 manual-real skipped`；Architecture/Repository Safety/Error Ledger PASS。

### M5.0 — 前端设计与契约固化

- M5.0 已完成以下文档固化：
  - `frontend/README.md` — 从 M1.3.2 状态升级为 M5.0 文档，新增动态回答原则、左侧栏能力边界、"+"菜单映射原则、模型选择器 DeepSeek 唯一交互、后端能力到 UI 映射表、M5 路线三段、项目/账户仅展示
  - `docs/01_product_scope_and_frontend_skeleton.md` — 全面重构为 M5.0 骨架规范，AI 回答动态渲染原则代替固定内容序列，Composer 结构、模型选择器交互、"+"菜单映射、项目/账户仅展示，后端能力映射表
  - `docs/specs/10_frontend_visual_and_interaction_spec.md` — 更新动态渲染规范（8.4 节完全重写代替固定顺序）、模型选择器只显示 DeepSeek、后端能力到 UI 映射表、"+"菜单映射原则、禁止固定内容序列
  - `docs/specs/11_structured_answer_contract.md` — 重写为动态渲染框架，删除固定内容顺序，新增 frontend rendering flow concept、ChatResponse 映射表、场景-展示对应表、删除 M1.4/M3 历史边界（已由 ADR-009 supersede）
  - `docs/04_powerbi_mcp_and_api_contracts.md` — 同步 ChatResponse 已实现的 report 字段和前端组合回答状态
  - `docs/07_milestones_status_and_open_questions.md` — 补充 M5.0 状态行，待确认事项标记 M5 阶段
  - `docs/08_development_roadmap.md` — M5 拆分为 M5.0/M5.1/M5.2 三段路线
  - `docs/09_context_handoff.md` — 标记 M5.0 已完成，下一步为 M5.1
  - `README.md` — 同步 M5.0 状态
  - `CHANGELOG.md` — 新增 M5.0 条目

### M4.4.2 final boundary closure

- 根因：SQLite `_model_to_work_memory()` 在 `payload_json` 缺失时用 dedicated columns 构造 partial `StructuredWorkMemory`；columns 不含 filters/time/sort/top_n/last_query_plan 等完整 canonical state，可能把损坏 committed state 解释为更宽查询。
- 最终语义：modern committed WorkMemory 的完整 domain reconstruction authority 仅为 `payload_json`。NULL/empty、malformed JSON、字段不完整、domain validation failure 或 row/payload integrity mismatch 全部 fail closed；dedicated columns 仅为 query/index/integrity/support fields，不再替代 executable semantic state。无 legacy partial reconstruction contract。
- `MemoryRepository.get_latest_committed()` / `list_by_conversation()` 的 runtime namespace 在 ABC、InMemory、SQLite 与 production callers 中 mandatory；删除跨模式 aggregate 默认行为。InMemory exact conversation/request ID 跨 Mock/Real overwrite 已由 composite conversation-store key 修复。
- 最终 audit 发现并最小修复两个额外 P1：非 legacy committed time corruption 不再在 StateTransition 静默清空；terminal Snapshot row/payload request/conversation/fingerprint/terminal mismatch 不再通过 replay。未发现 P0；未做大重构或未来功能。
- M0—M4 semantic/DAX/fact/report/memory/snapshot/namespace/filesystem authority 保持封板模型；Real failure 不回退 Mock，history/persistence 不成为 factual authority，report HTML 继续只从 filesystem 恢复。

### M4.4.1 corruption boundary

- 根因：`StructuredWorkMemory.filters` 接受任意 `dict`，SQLite `model_validate()` 无法识别 semantic corruption；`StateTransitionService._previous_filters()` 又捕获 canonical parse failure 后 `continue`，导致损坏 filter 被解释为空并可能扩大下一轮查询范围。
- 修复：保持 `list[dict]` storage/legacy shape，但 domain validation 逐项调用 `StructuredFilter.model_validate()`；持久化损坏在 fresh repository load 时以 `committed_memory_filter_invalid:<index>` fail closed。StateTransition 对绕过初始 validation 的进程内损坏抛出 `CommittedMemoryCorruptionError`，禁止 skip/clear/default-empty。
- TurnPipeline 的 committed/pending load、context build 与 controller setup 现在复用 Owner abort-on-exception 语义；同一 request_id 在 corruption 后可重复得到确定性失败，不遗留永远等待的 process-local claim。
- 合法 committed filter 继续跨轮继承；已有 legacy time string contract 保持不变。无 persistence schema change、无 Alembic migration。
- 新真实临时 SQLite restart regression 使用 dispose + fresh engine/repository/service，参数化覆盖 Mock/Real。同 namespace 在 LLM、schema、DAX、Power BI 与下一 memory commit 前失败，version 保持 1；另一 namespace 的合法 filter 正常恢复。
- README 现固定为 value-first Landing Page；`AGENTS.md` 新增 README Maintenance Contract。正式 PRD 只同步实现状态，07/08/09 与 CHANGELOG 同步为 M4.4.1。

### M4.4 restart / crash authority

- terminal `result_snapshots` 是 request replay authority；durable Snapshot 已保存但 process-local tracker 尚未 complete 时，fresh runtime 直接 replay，不重复工具执行。
- process-local in-flight claim 不持久化；crash 后若无 Snapshot，不产生 fake completed。若同 request 已有 Memory 但缺 terminal Snapshot，表示结果/外部副作用无法安全确认，TurnPipeline 以 `IdempotencyCoordinationError` fail closed，不自动重执行，也不生成 terminal duplicate。
- committed Memory 按 `(runtime_mode, conversation_id)` 恢复并保持 version；Pending/Failed 不冒充 Committed。Mock/Real 同 conversation ID 持续隔离。
- SQLite/History/Snapshot 仍不是 business/result/report factual authority；M0—M3 truth chain 未改。

### Report recovery

- `report_artifacts` SQLite row/payload 继续只提供 strict metadata；HTML filesystem 是唯一内容 authority。
- 新 persistent `ReportResultSnapshot` 的 `html` 兼容字段为空；restart replay 通过 `ReportRepository.read_html()` 读取文件，并核对 report identity、template/contract/reference/content hash、conversation/request linkage 与 source mode。
- Adaptive Real report 路径现将实际带 `conversation_id/request_id` 的 `ReportSpec` 传给 ToolGateway；此前构造 context copy 后误传原对象的生产 bug 已由严格 replay 验收发现并修复。
- missing/tampered HTML、corrupt metadata 或 snapshot/artifact mismatch 均 fail closed。配置了 report repository 时，旧 snapshot 内可能存在的 HTML 也不参与重放 authority。

### History / Archive / Delete restart

- recent/history/search/reports 在 dispose + fresh engine/service 后与重启前一致；archive 状态保留，recent/search 默认隐藏，direct history/reports 继续遵守 M4.3 contract。
- Migration `c8d4e6f2a109` 新增 `conversation_delete_intents`：DB 删除 transaction 同时持久化 exact `(runtime_mode, conversation_id)` 的 report IDs/counts；HTML cleanup 成功后 service 才清除 intent。
- DB commit 后 unlink/finalize 失败或进程退出时，fresh service 的相同 delete 可从 intent 重试；pending intent 阻止 Memory/Snapshot/Report 在该 namespace 复活。成功 delete 后再 restart，DB state、intent 与关联 HTML 均已清理；另一 namespace 不受影响。
- 这是应用级 durable intent + idempotent cleanup，不声称 SQLite transaction 可原子覆盖 filesystem，也不声称硬件/文件系统违反自身 durability contract 时仍可恢复。
- Report create 仍是 atomic HTML write → metadata save，并在可观察的 metadata-save failure 上 best-effort unlink；M4.4 没有为进程恰在 HTML rename 后、metadata commit 前退出的窗口增加 durable create journal，因此不承诺自动回收该无引用文件。该窗口不会形成成功 metadata 或 terminal Snapshot，也不会被当作可恢复报表。

### Fresh acceptance

- 新增 7 个 restart/crash integration tests；每个 restart 路径都使用真实临时 DB/files、dispose、全新 engine/session/repository/service。
- 新增 1 个 M4.3 → M4.4 migration test；fresh DB → head 与 `f4c3a2b1907d` → head 均通过。
- Backend fresh regression：`1681 passed, 1 skipped`。
- Golden `11 passed, 1 manual-real skipped`；Architecture `109`、Repository Safety `239`、Error Ledger `25`、Documentation Governance PASS。
- `backend/app/config/settings.py`：version → M4.4。
- M4 FINAL PASS；不新增 Tag。

### M4.4.1 fresh acceptance

- Targeted corruption regression：5 passed（StateTransition 3；真实 SQLite restart 2）。
- 邻近 Memory/StateTransition/persistence/restart：190 passed；backend full regression：1686 passed、1 skipped。
- Golden：11 passed、1 manual-real skipped；Architecture `109`、Repository Safety `239`、Error Ledger `25`、Documentation Governance PASS。
- Alembic head 保持 `c8d4e6f2a109`；fresh DB → head 与 head → head 幂等 upgrade PASS，确认无新增 migration。
- `backend/app/config/settings.py`：version → M4.4.1。
- M4.4.1 无 migration；M5 NOT STARTED；不新增 Tag。

### M4.4.2 fresh acceptance

- Payload/namespace/audit targeted + adjacent suites：`607 passed`。
- Backend full regression：`1700 passed, 1 skipped`。
- Golden：`11 passed, 1 manual-real skipped`；Architecture `109`、Repository Safety `239`、Error Ledger `25`、Documentation Governance PASS。
- Alembic head 保持 `c8d4e6f2a109`；fresh DB → head 与 head → head 幂等 upgrade PASS，确认无新增 migration。
- `backend/app/config/settings.py`：version → M4.4.2。
- M4.4.2 FINAL PASS；M5 NOT STARTED；不新增 Tag。

### M5.5 fresh acceptance

- `火星区销售额` clarification 且 ZERO DAX/QueryResult/Memory commit；`华南/华南区/南区` 仅经 runtime member authority 解析为 `South`。
- Real Rich PBIX 四轮 `2025年5月销售额 → 那南区呢 → 换成去年 → 前三个产品呢` 正确保留/替换 measure、time、filter、dimension、sort 与 Top3。
- deterministic ranking grammar、temporal filter/grouping、READ_ANALYSIS 与 prediction/delete unsupported policy 通过；unsupported 同样 ZERO DAX。
- Sales、Education、Inventory、开发期未知 opaque holdout 与 schema mutation gates 通过；生产 semantic code 无 sales-specific object/member hardcode。
- Backend full `1823 passed, 1 skipped`；frontend Vitest `69 passed`、typecheck/lint/build PASS；Golden `11 passed, 1 manual-real skipped`；Architecture `118`、Repository Safety `296`、Error Ledger `32`、Documentation/Artifact Governance、compileall 与 Local MCP readonly smoke PASS。
- Real API/Browser/manual acceptance 通过；automation-owned conversation/report/file/SQLite/delete-intent residual=0。用户 `.env` 存在既有格式错误，未修改、未输出内容；不影响本轮已完成的 configured DeepSeek + Local MCP Real acceptance。

### M5.7 fresh acceptance

- missing/invalid/stale template 均在 ReportData/ReportSpec/Renderer/HTML artifact 前 fail closed；Real spy 的 no-template 路径仅调用 `intent_recognition`，下游计数均为 0。
- 当前 `sales_report` 正式展示为“简易模板”；前端无默认值，显式选择后才传 `report_template_key`，普通 data question 不受 selector 影响。
- Browser visual matrix 共 42 组（`1/2/6/12/15/24/60` points × `390/768/1080/1440/1920/2560` width）通过，无页面水平滚动、tick/direct-label clipping、tick overlap 或 donut/legend overlap。
- Rich PBIX Real Browser 验收通过：未选模板两次均提示选择且无 report；显式选择后生成 15 点跨年趋势、分类 donut/legend 与区域对比；真实分组问题继续展示准确 table/chart。
- 本轮 automation-owned conversation、两份 report 与 HTML 已经正式 API 清理；SQLite namespace、delete intent、ownership registry residual=0。
- Fresh final gates：backend `1866 passed, 1 skipped`；frontend typecheck/lint/build PASS、Vitest `80 passed`；Golden `11 passed, 1 manual-real skipped`；Architecture `120`、Repository Safety `303`、Error Ledger `35`、Documentation/Artifact Governance、compileall 与 `git diff --check` PASS。

### M5.7.1 completed contract and fresh acceptance

- P0 根因：完整 SemanticGrounding 在出现显式时间时仍要求唯一 Date/DateTime 或唯一 glossary 日期字段；Rich 模型同时存在 `Sales[OrderDate]`、`Date[Date]` 与 grouping 字段，导致 TimeGrounder 已解析的 `2025-05-01..2025-05-31` 被错误 clarification。
- 最终 date-role resolver：用户显式日期角色 → 唯一 model-scoped `temporal_role: default` → 唯一 temporal-grouping binding → 唯一 glossary 日期对象 → 唯一 runtime 日期字段 → clarification。无唯一证据、unknown member 与 unsupported capability 均继续 ZERO DAX/Memory commit。
- 时间解析覆盖绝对月份、`2025-05`、今年/去年指定月份、上月、季度/Q1、最近 N 月与 NFKC 全角；64 组 seeded metamorphic wording、语序/标点、multi-turn KEEP/REPLACE、TopN、Sales/Education/Inventory/unknown holdout 与 schema mutation 均通过。
- 永久 `scripts/check_semantic_compatibility.py` 已接入 CI，检查 canonical slots、ZERO-DAX 边界、answer leakage、frontend factual authority 与 provider-specific semantic authority；最终治理把 leakage scan 扩大到完整 `backend/app/**` production `.py/.yaml/.yml/.json/.toml`，并禁止 production import/read/depend on known-answer cases、baseline、oracle 或 test-only truth。当前扫描 103 个 production backend 文件，无真实 leakage 或非法依赖，Semantic suite 保持 `302 passed`。
- `PowerBIAgent Validation` 已将 `m5/rebuild` 纳入 push 与 pull request 触发；Semantic Compatibility Gate 固定在 full pytest 之前，不使用真实 Secret、Power BI 或 `.env`。
- Remote execution evidence：commit `919affd29d6ab35429c6fd6fe55a799f8882b760` 的 `m5/rebuild` push 已触发 [PowerBIAgent Validation #36](https://github.com/Strange-Men/PowerBIAgent/actions/runs/33037609916)；job `98403716751` success，公开 Actions step evidence 显示 `5. Semantic Compatibility Gate`、full pytest、Golden 与 strict git check 均为 `completed/success`。
- Fresh final gates：backend `1908 passed, 1 skipped`；frontend Vitest `80 passed`、production build PASS；Golden `11 passed, 1 manual-real skipped`；Repository Safety `306`、Architecture `120`、Error Ledger、Documentation/Artifact Governance、compileall 与 `git diff --check` PASS。
- Rich PBIX API/Browser/manual 覆盖总销售额、绝对/相对月份、趋势、South、unknown member、readonly approximation、future prediction 与四轮 `2025年5月销售额 → 那南区呢 → 换成去年 → 前三个产品呢`；automation run `m571-real-20260827` 清理后 conversations、work memories、snapshots、reports 与 delete intents residual=0。
- 未弱化 M5.5 semantic/DAX/VerifiedFactSet authority；未修改报表视觉或 Template/Renderer Registry；未开发 DeepSeek/Kimi；未修改 MCP performance。

### M5.7.2 completed contract and fresh acceptance

- Report Gate 固定在 Intent 后的 `TurnPipeline.preflight_report_template()`；missing/unknown/stale template 使用同一精确提示，DeepSeek spy 证明只调用 `intent_recognition`，schema/DAX/repository/report downstream 均为 0，普通问答不被拦截。
- 后端以 `ReportTemplateRegistry`、`ReportRendererRegistry` 和 `ReportRendererDispatcher` 建立单一 authority；只读 `GET /api/v1/report-templates` 向前端提供唯一公开的 `sales_report / 简易模板`，无 default、隐式选择或 first-item fallback。
- 前端删除硬编码模板权威表，动态读取后端目录；未选择显示紧凑状态，显式选择后显示“已选 简易模板”，stale selection 自动清除，聊天区只在真实报表请求失败时显示一次 runtime reminder。
- 简易模板固定顺序为 4 KPI → 月度趋势 → 区域/品类 → Top 产品 → 关键明细 → 数据来源/最后刷新；趋势包含 deterministic nice Y ticks、水平 gridlines、`销售额（元）`、全部 data points、桌面 15 月完整标签，以及小屏 first/last/year-boundary 双层确定性 tick。
- 完整 deterministic visual fixture 在 390/768/1440/2560 均无水平滚动或 label overlap，15 点全部保留；1440/2560 显示全部 15 月，完整覆盖区域、品类、Top 产品、关键明细与 footer。Real `PowerBIAgent_M3_Rich_Test` 当前 runtime schema 实际只证明 4 KPI、15 月趋势和品类，Region/Product/Customer 三项被 capability gate 标记 unavailable 并正确省略，未伪造 section。
- Fresh gates：Semantic Compatibility `304 passed`；backend `1918 passed, 1 skipped`；frontend Vitest `83 passed`、typecheck/lint/build PASS；Golden `11 passed, 1 manual-real skipped`；全治理、compileall 与 `git diff --check` PASS。automation run `m572-real-20260827-a1` 的 conversation/report/HTML/delete-intent 与 ownership residual=0。
- `PowerBIAgent Validation` 已在既有 security/architecture/docs/Semantic/full pytest/Golden/strict-git gates 之外接入 Node.js 24 LTS + `npm ci`，并将 frontend Vitest、typecheck、lint 与 production build 作为四个不可跳过的远程失败门禁；Vitest 跨文件串行以消除 Windows 冷安装时的 worker 启动竞争，不修改测试断言或超时。final commit SHA 与 Actions run evidence 只在提交后最终报告中记录。
- M5.7.1 Semantic/DAX/VerifiedFactSet/Memory authority 未修改；未开发 DeepSeek/Kimi Provider、未修改 MCP、未新增第二模板、无 schema/migration。

## M5.8 完成合同

- 唯一范围：共享 OpenAI-compatible Provider、`LLMModelProfile`、DeepSeek/Kimi profiles、显式 request/conversation selection、统一 error/usage/trace 与前端选择器。
- 每个 turn 在入口解析 public profile key 并固定 provider/profile snapshot；禁止 global mutable default、自动路由、ensemble 与 DeepSeek↔Kimi fallback。同轮 Intent/QueryPlan/Answer 不得隐式混用 provider。
- 新会话使用提交时显式选择；同会话下一轮可切换。切换不清空 Structured Memory/canonical slots，也不把 provider opaque session state升级为 factual/semantic authority。
- malformed/wrong-shape structured output 最终以 provider-independent validation error fail closed；不得创造缺失 semantic field/value，错误 turn 不得错误提交 authoritative Memory/facts。
- trace 仅含 public profile/model/protocol/task/usage/error class；Key、Authorization、Secret URL query、完整 prompt 与原始敏感响应禁止记录。pricing 缺失时 estimated cost 为 null。
- M5.7.1 Semantic/DAX/VerifiedFactSet/Memory 与 M5.7.2 Report Template/Renderer authority 均冻结；禁止 MCP 性能、第二模板、Remote MCP、多模态、LangGraph、多 Agent。
- 固定 checkpoint 为 S1—S14；S1—S13 与本地 S14 gates 已完成，最终 commit/push/exact-HEAD CI 证据以本轮交付为准。

### M5.8 实现与 fresh evidence（COMPLETE）

- 已实现不可变 profile、共享 OpenAI-compatible HTTP Provider、显式 Registry、request-scoped snapshot、DeepSeek/Kimi 配置与目录、统一 error/usage/trace，以及 frontend backend-owned 模型选择；无 `set_default()`、自动路由或 provider fallback。
- focused Provider/API/selection/concurrency/switch tests 已通过；CI 等价 Mock/Memory full backend 为 `1940 passed, 1 skipped`；永久 Semantic Compatibility 为 `306 passed`（106 个 production backend files）；Golden `11 passed, 1 manual skip`；frontend 为 `86 passed`，typecheck/lint/build 通过；Repository Safety `314`、Architecture `123`、Error Ledger `37`、Documentation/Artifact Governance、compileall 与 `git diff --check` 通过。
- Real DeepSeek/Kimi 均已配置并对同一 `PowerBIAgent_M3_Rich_Test` 运行总销售额、2025 年 5 月、区域、月趋势、Top3、四轮 KEEP/REPLACE、unknown member、prediction 与 `sales_report`。两个 profile 的 canonical plan/规范化 QueryResult 相同；profile mismatch=0、并发隔离、mid-conversation switch、DAX/Answer LLM 调用为 0、固定报表与 residual=0 均通过。
- 旧 M2 frozen numeric oracle 与当前 Rich PBIX 值域不同，仅作为协议/控制面观察，不修改 oracle 或生产 Semantic/DAX 迁就旧值。Real 长序列中的偶发 Local MCP `ToolExecutionError` 按基础设施失败记录；独立边界复验全绿，未跨入 M5.9 性能/session/cache 修复。
- Provider 错误和非 Provider turn 异常均保留安全 public profile/model/protocol；Provider 错误额外携带统一 category/class。响应不包含 Key、Authorization、endpoint、prompt 或原始敏感 payload。

### M5.8.1 实现与 fresh evidence（COMPLETE）

- Local MCP 由 application-owned owner task 持有单一 read-only stdio worker/client；session generation 隔离 tool discovery 与 metadata cache，MCP crash 后安全失效重建，FastAPI shutdown clean close。模型访问仍重新枚举 Desktop 并精确匹配唯一 opaque identity，PBIX 切换/重启/stale/validation failure 均 fail closed，禁止 list-order 选择或 fallback。
- 进程内 bounded TTL/LRU 仅覆盖 tool discovery、Desktop discovery、成功 compatibility、schema 与 bounded member metadata；member key 包含 semantic model identity、schema fingerprint、table/field/normalized request/limit。per-key async singleflight 合并 startup/discovery/probe/schema/member 重复工作，最小 semaphore/queue 防止无界 MCP operation；未引入 Redis、distributed cache 或完整 M5.9 backpressure/soak。
- performance trace 使用 monotonic clock，仅含 operation、duration、cache 与 session 状态。优化前 metadata cold/warm 为 discovery `6297/7860ms`、schema `9078/10172ms`、member `19422/20890ms`、DAX `11047/8094ms`；优化后为 discovery `3782/0ms`（startup `3406ms`）、probe `1468/157ms`、schema `422/156ms`、member `515/172ms`、DAX `485/515ms`。full-turn 冷启动旅程 `18172ms`；热态 10 轮 `13000ms`（单轮 `1000–1891ms`），4 路小并发 `3719ms`。首次两轮外部 LLM 波动 `9250/17922ms` 已如实保留。
- session/cache/stale/failure/cancellation/PBIX isolation 单测 `91 passed`；20 路相同 schema 与 member lookup 各只执行一次 underlying read，failure 不污染 cache，普通 DAX 连续两次均真实执行。Semantic Compatibility `306 passed`（108 production files）；backend `1950 passed, 1 skipped`；frontend `86 passed` 且 typecheck/lint/build PASS；Golden `11 passed, 1 manual-real skipped`；Repository Safety `318`、Architecture `125`、Error Ledger `37`、Documentation/Artifact Governance、compileall 与 `git diff --check` PASS。
- Rich PBIX Real 双 Provider acceptance 覆盖总销售额、2025 年 5 月、华南区、Top3、multi-turn、report、并发隔离与 mid-conversation switch；canonical plan、DAX、QueryResult、Memory、Report 行为不变，cross-provider plan/result digests 相同，residual=0。Answer/Report HTML/Canonical QueryPlan/DAX result/QueryResult/VerifiedFactSet 均未缓存；M5.8 Provider 与 Semantic/Time/Member/TopN/DAX/Report authority 未修改。

### M5.8.2 实现与 fresh evidence（COMPLETE）

- `QuestionRouter` 在共享 TurnPipeline 的 Context/LLM/schema/member/DAX 前判定能力类别；PRODUCT_HELP、SYSTEM_INFO、DETERMINISTIC_CALC 与 UNSUPPORTED_GENERAL 直接返回，保留已有 PendingClarification 且不提交 semantic Memory。REPORT_REQUEST 只对齐既有 report intent，继续由 M5.7.2 Template Gate 负责。
- Query Shape 固定为 SCALAR、ENTITY_LIST、GROUPED、RANKING、MEMBER_SET、FILTERED_AGGREGATION、TREND、BOUNDED_TREND。required slots 按 shape 计算；dimension-only distinct、Top1、同字段 runtime-validated `IN_SET`、跨月闭区间与仅缺指标的 minimal clarification 已进入 Canonical QueryPlan、Deterministic DAX 与独立 verifier。
- 多轮仅在当前表达明确新 shape 时替换；`销售额是多少 → 那各地区呢 → 最高的是哪个 → 换成销量 → 只看华南` 保持唯一已提交维度、ranking Top1 与明确 measure/filter 替换。non-business turn 不改变 committed 或 pending semantic state。
- Sales/Education/Inventory/unknown holdout 的 SCALAR/ENTITY_LIST/GROUPED/RANKING/MEMBER_SET/TREND、schema mutation、unknown member/ZERO DAX 与 leakage scanner 均通过。Semantic Compatibility `421 passed`（109 production backend files）；backend `2046 passed, 1 skipped`；frontend `86 passed` 且 typecheck/lint/build PASS；Golden `11 passed, 1 manual-real skipped`；Repository Safety `323`、Architecture `126`、Error Ledger `37`、Documentation/Artifact Governance、compileall 与 diff check PASS。
- Rich PBIX Real 15 项题集全部通过：6 个可执行业务问题完成并提交，ambiguous ranking 只澄清 measure，2 个不存在成员的问题 runtime no-match 且 ZERO DAX，6 个 non-business 问题 ZERO schema/DAX/Memory；residual=0。M5.8.1 性能复验保持 metadata cache/session reuse，稳定 10 轮 `16156ms`、4 路并发 `4469ms`；外部 LLM 长尾未归因于 MCP。
- 未开发 M5.8.3 ModelSemanticContext、M5.9/M5.10；未修改 Provider、M5.8.1 MCP session/cache/singleflight/concurrency 或 Report renderer/template；未引入 Redis/RAG/Ontology。M5 FINAL=false。

## 下一步

M5.8.2 已完成。下一阶段为 M5.8.3 MCP-driven ModelSemanticContext 与任意 PBIX 通用语义适配；完整 MCP queue/backpressure、20/50/100、fault/restart/soak 仍属于 M5.9，固定专业销售模板属于 M5.10。M5.8.3 当前验收收口，M5.9/M5.10 未开始，M5 FINAL=false。

## 关键命令

```powershell
# Full test suite
D:\Conda\envs\PBIAgent\python.exe -m pytest backend\tests -q --asyncio-mode=auto

# Permanent Semantic Compatibility Gate
D:\Conda\envs\PBIAgent\python.exe scripts\check_semantic_compatibility.py

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
D:\Conda\envs\PBIAgent\python.exe scripts\check_artifact_governance.py
```

## 本地启动（PowerShell 标准流程）

先执行一次 `conda init powershell`（首次使用），然后关闭并重新打开 PowerShell：

```powershell
conda activate PBIAgent
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm install
npm run dev
```

验证 Python 路径：`python -c "import sys; print(sys.executable)"` 应输出 `D:\Conda\envs\PBIAgent\python.exe`。

常见问题见 `README.md` 的"常见启动问题"。

---

*最后更新：2026-08-31 | M5.8 / M5.8.1 / M5.8.2 COMPLETE；M5.8.3 验收收口（发布见对应提交 CI）；M5.9 / M5.10 NOT STARTED；M5 FINAL 尚未成立*
