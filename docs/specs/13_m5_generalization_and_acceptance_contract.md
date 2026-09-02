# 13 — M5 重建、泛化与验收契约

> **状态：** M5.5 / M5.6 / M5.7 / M5.7.1 / M5.7.2 / M5.8 / M5.8.1 / M5.8.2 / M5.8.3 / M5.8.4 COMPLETE；M5.9 / M5.10 NOT STARTED；M5 FINAL 尚未成立
> **适用范围：** `m5/rebuild` 开发线及 M5.5—M5.10（含 M5.7.1 / M5.7.2 / M5.8.1 / M5.8.2 / M5.8.3 / M5.8.4）
> **基线：** M5.4.1 commit `cab40b076f054a3ebdab0bf6d2b0354f4b2d49db`
> **性质：** 长期工程与验收合同；M5.5 已按此合同完成，后续阶段继续受本合同约束

## 一、重建基线与历史真实性

新开发线必须从 M5.4.1 稳定基线 `cab40b076f054a3ebdab0bf6d2b0354f4b2d49db` 开始。以下旧实验线作为研究和失败经验永久保留：

```text
m5/frontend
├─ a197db3ecfe8959f3f8bb79e18d7ee02834fedd3 — 原 M5.5
└─ 6d1620a7a7aa04e65692371436d90756fdf5bcc8 — 原 M5.5.1
```

它们不得删除、revert、rebase 或重写，不得整体 cherry-pick 到新线。后续可以参考单项设计思想，但每项能力都必须在所属新里程碑中重新实现、重新建立回归证据并重新完成 Real Acceptance。正式记录不得把这段实验历史伪装成“从未发生”，也不得把旧 PASS 数字冒充新线证据。

M5.4.1 及以前的以下能力不可回退：

- Agent-first 前端、Local MCP readonly；
- 多 PBIX opaque identity、exact selection 与 stale fail closed；
- TurnPipeline、Memory、Deterministic DAX、QueryResult / VerifiedFactSet factual authority；
- M5.3.3 多轮基础语义；
- conversation-scoped state、异 conversation 并发、同 conversation 串行；
- Settings 全量 cursor pagination 与 conversation/report resource lifecycle；
- archive ≠ delete、report tombstone；
- automation ownership、residual=0、unknown ownership 用户资源不得自动删除。

M5.8.3 的结构 authority 固定为 Power BI MCP Runtime Semantic Model；immutable ModelSemanticContext 仅适配当前模型 metadata；optional model override 仅补充业务语言/temporal metadata，必须通过 exact identity + schema fingerprint 和 runtime object validation。LLM 只能在 runtime-owned candidate IDs 中有界选择，QueryResult/VerifiedFactSet 仍为 factual authority，不建立第二套模型或数字来源。当前异构 fixture 五形态、真实 Rich15/零配置/完整 Chat/Memory/member A→B→A/facts 与本地 full gates 已通过；临时目录已统一受控 finally/ownership 校验，常规流程不再要求人工删除；cleanup failure 仅 warning + truthful residual。正式 COMPLETE 以 fresh local/residual 与新 exact-SHA CI success 为条件。证据见 [M5.8.3 计划](../milestones/m5/m5_8_3_model_semantic_context_plan.md)。

## 二、真实用户测试问题账本

M5.8.4 经用户明确批准，扩展现有 runtime Catalog 内的跨语言 linguistic selection。普通中文查询不以模型专属 glossary 为前提；对象/成员只映射当前 runtime candidate ID；exact identity/fingerprint/session isolation 不变。完整合同见 [Model Context spec](model_semantic_context.md) 与 [ADR-015](../adr/ADR-015_cross_language_runtime_grounding.md)。M5.8.3 的 COMPLETE 已由 `b86662e` 的 CI success 核验；M5.8.4 主开发提交 `41b6e0b` 后首次 CI #33455159267 因测试 reference date 漂移失败，`a975310` 修复测试时钟后 CI #33457056546 completed/success，M5.8.4 COMPLETE。最终治理提交仍须以自己的新 exact-SHA CI success 作为最新封板证据。

### 2.1 Semantic / capability

- “火星区销售额”不得因 member 无匹配而降级为全国销售额。任何 explicit member/filter 无法权威解析时，必须 clarification 或 no-match，并且 **ZERO DAX**。
- “华南”“华南区”“南区”不能由代码猜同义，必须以当前模型的 runtime member authority 和受控语义证据解析；不能唯一证明时 clarification。
- prediction、write、delete、modify 等能力边界近义词不能依赖无限扩张的 regex；“大概多少”不得被误判为 prediction。最终 capability 结论必须由 bounded evidence + deterministic policy 决定。
- TopN/ranking 不得因不必要的 LLM failure 完全失效；canonical ranking slots 与执行必须继续遵守 deterministic authority。
- 生产代码不得为 Sales 写死答案、字段或 member。

核心 Gate：

```text
explicit unresolved semantic requirement
→ clarification / no-match
→ ZERO DAX
```

### 2.2 Multi-turn / temporal

以下真实 follow-up 必须按当前明确表达正确 KEEP/REPLACE slot：

```text
2025年5月销售额
→ 那南区呢
→ 换成去年
→ 前三个产品呢
```

- 第二轮替换区域筛选，保留 measure 与时间；
- 第三轮只替换时间，保留 measure 与兼容筛选；
- 第四轮增加/替换 ranking dimension、sort、top_n，不能因当前轮未重述 measure 就丢失 measure；
- 任何成员歧义或 no-match 都不得借旧 Memory 继续执行。

canonical 时间值可继续作为内部权威表示，但 UI 不得直接展示类似 `Year Month=2025-01-01T00:00:00 ...` 的内部 representation。

### 2.3 Presentation / resource UX

职责固定为：

```text
Answer = 洞察
Table = 明细
Chart = 趋势 / 关系
```

Answer 不得完整重复 table。展示层必须保持 canonical/display separation，不得用本地化或格式化改写 QueryPlan、DAX、QueryResult 或 VerifiedFactSet。

后续必须分别解决：

- Settings 有 report 时 Recent Reports 必须同步反映同一资源 truth；
- Recent conversation 必须 newest-first；
- failed conversation 必须作为正式资源可查看、重试或删除；
- toolbar 空间不足时不得隐藏 destructive actions，必须采用 sticky、scroll 或 responsive toolbar；
- conversation/report action menu 不得被 overflow clipping。

### 2.4 Report readability

“技术不裁切”不等于“产品可读”。报表必须合理利用 card width/height，时间轴可识别且跨年份清晰，plot area 比例合理，不出现巨大无意义空白，donut/legend 信息密度合理，并通过 Real Browser 人工视觉 Gate。

### 2.5 Performance / MCP lifecycle

旧实验线曾观测到 Real latency 从几十秒到数分钟；schema/member/DAX 重复 session 有明显成本。persistent worker 是可参考思路，但 queue、backpressure、TTL、stale、异常恢复必须在 M5.9 独立压力验证。必须分别报告 cold 与 warm latency，禁止用 warm latency 冒充 cold latency。

## 三、M5.5—M5.10 分阶段边界

### M5.5 — Semantic correctness and capability boundary

只允许开发：

- semantic grounding；
- runtime member validation；
- ambiguity / no-match；
- multi-turn KEEP/REPLACE；
- ranking / TopN；
- temporal semantic contract；
- capability boundary。

禁止：Localization、Report Visual、MCP performance optimization、Resource UI 大改。M5.5 的首要验收是 explicit unresolved semantic requirement 必须 clarification/no-match 且 ZERO DAX。

#### M5.5 canonical semantic contract

- object role 固定为 `measure / dimension / filter_field / date_field / ranking_dimension`；解析顺序为 runtime canonical exact → approved model-scoped alias exact → metadata evidence → bounded candidate-ID selection → ambiguous/no-match。
- business member 与 object grounding 分离：user literal → target field candidate → deterministic alias/morphology candidate → optional bounded language candidate → runtime `ColumnMembers` exact validation → canonical runtime member。无匹配、多个 field 命中或多个 member 候选都不得执行。
- slot 独立决策 `measure / dimensions / filters / time / ranking / sort`，优先级为 current explicit evidence > current bounded semantic draft > compatible committed Memory。fresh query 清除无关旧槽；follow-up/replace 只继承真正省略的兼容槽。
- 高置信 ranking grammar 确定性提取“前N个/Top N/最高的N个/最低的N个”的 `top_n`、direction 与 ranking intent；ranking dimension/measure 仍由 runtime grounding 决定，不能由 grammar 猜对象。
- temporal contract 区分 time filter 与 temporal grouping，首批 registry 支持 explicit month/year、relative month/year、recent N months、bounded range、month/year grouping。runtime 不支持 requested grouping 时 controlled unsupported/clarification，禁止 HTTP 500。
- capability 使用三层：deterministic safety floor；只输出 `READ_ANALYSIS / FUTURE_PREDICTION / MODEL_WRITE / DATA_DELETE / ARBITRARY_CODE / UNKNOWN` 的 bounded classification；deterministic policy 终审 supported/clarification/unsupported。“大概多少”不得因单一词误判为 prediction。
- semantic trace 至少记录 request/conversation ID、current explicit slots、inherited slots、object/member grounding status、capability decision、canonical plan summary/hash、DAX executed 与 Memory committed；不得记录 Secret 或 raw full prompt。

### M5.6 — Presentation, localization and resource UX truth

只允许开发：

- canonical/display separation；
- model/object/schema-scoped Localization；
- number/date/month formatting；
- Answer/Table/Chart 信息密度；
- Settings/Recent resource truth、newest-first；
- failed resource lifecycle；
- sticky/scroll/responsive toolbar 与 floating menus。

conversation 与 report 必须共用同一 Portal/floating layer action menu，按 viewport 在目标行上方或下方定位；禁止分别维护两套易漂移逻辑，且不得被 scroll container、scrollbar 或 stacking context 裁切。Settings Resource Manager 必须有 nested scroll contract 与 sticky 或 scrollable action toolbar，responsive overflow 不得吞掉 destructive actions。

Localization binding 最小字段固定为 `semantic_model_key / object_identity / object_type / canonical_name / locale / display_name / source / schema_identity`；metadata → model glossary → persisted registry → bounded runtime-object translation → safe fallback 是唯一优先级。canonical identity/value 永不因 display 改变，schema/object identity 变化使旧 cache 失效，unknown object 不可被 LLM 创造。

Presentation density 固定为 scalar 纯自然语言、grouped 简短结论 + table（必要时 chart）、trend 简短趋势洞察 + table + line。formatter 覆盖 integer/decimal/percentage/currency/date/month/null，raw ISO timestamp 不可见；table/chart header 本地化不得依赖 production frontend 的 Sales-specific 字典。

Resource truth 固定为 Settings 全量 query 与 Sidebar 同源 bounded projection；reports active newest-first，conversation `updated_at DESC, created_at DESC, stable_id DESC`。failed conversation 持久化并可 rename/archive/restore/delete，状态只来自正式 backend metadata。

正式 Layout Gate 至少覆盖：first/middle/last row、scroll top/middle/bottom、100%/125% zoom、768/1080/1440 viewport height、Sidebar scroll、Settings nested scroll、destructive action 始终可访问、floating menu 永不裁切。

禁止修改 Grounding authority、DAX authority 与 MCP architecture。

### M5.7 — 简易报表视觉 + Report Template Required

只允许开发：

- 现有 `sales_report.html` 作为“简易模板”的 report information architecture；
- responsive layout；
- plot geometry、axis/tick density；
- accessibility、visual hierarchy 与 report readability；
- 前后端显式模板选择与 Report Template Required Gate。

任何 report intent/request 必须显式携带 registry-valid `report_template_key`。missing/invalid/stale template 必须返回 clarification/template-required，并在 ReportData assembly、ReportSpec、Renderer 与 HTML artifact 前停止；禁止默认 `sales_report`、自动猜模板、fallback 第一项或未选择仍继续生成。前端 selector 只提供 template choice，不自行判断 intent，不增加 Chat/Report 模式切换器。

时间趋势 Gate 覆盖 1/2/6/12/15/24/60 点、390/768/1080/1440/1920/2560 宽度、单年/跨年、首尾极值、长标签、大数值与中文月份；first/last tick、direct label 与 tooltip 必须完整可读，无页面水平滚动，tick density 随宽度与点数自适应。KPI/card 不得有巨大空白，donut/legend/table 必须在大小屏可读，semantic heading、accessible name 与 visible focus 必须存在。正式 Gate 是“普通用户必须能读懂报表”，不能只证明 SVG 未越界。

禁止修改 M5.5 Semantic/StateTransition/DAX/VerifiedFactSet authority、M5.6 Presentation authority、MCP、LLM Provider 或 resource lifecycle；不开发专业销售模板。

### M5.8 — 多 LLM Provider 抽象 + DeepSeek/Kimi 最小双模型

仅在 M5.7 冻结后开始，只允许：

- `OpenAICompatibleLLMProvider`；
- `LLMModelProfile`；
- DeepSeek + Kimi-K2.6；
- request/conversation-scoped model selection；
- 两个模型共用同一 authority 与 regression contract。

禁止 MCP profiling、session reuse、cache、concurrency 或 queue/backpressure 优化；不得改变 Grounding、DAX 或 VerifiedFactSet authority。

#### M5.8 Provider / selection contract

- `LLMModelProfile` 至少包含 `profile_key`、`display_name`、`provider_protocol`、`base_url`、`model`、`timeout`、协议 capability flags 与可选 pricing metadata；Secret 不属于 public profile。
- DeepSeek/Kimi 共享唯一 `OpenAICompatibleLLMProvider` HTTP 实现；禁止 `KimiTurnService`、`KimiIntentService`、`KimiQueryPlanService`、`KimiAnswerService` 或复制 client。
- Registry 以 `profile_key` 显式解析 provider/profile。用户切换不得调用 `set_default()` 或写入任何进程级 mutable default；unknown/stale/unavailable profile 必须 fail closed。
- Chat request 携带安全 public profile key。每个 turn 在开始时创建 immutable selection snapshot，并注入全部 LLM tasks；in-flight turn 不受 UI 后续切换影响，不允许同一 turn 混用 DeepSeek/Kimi。
- conversation 可保存安全的 profile identity audit metadata，但 profile 不是 semantic model identity、canonical slot、DAX 或 factual authority。中途切换保留兼容 Structured Memory。
- OpenAI-compatible wire contract 为 `POST {base_url}/chat/completions`、Bearer auth、`stream=false`、deterministic temperature/config、structured JSON、usage、finish reason 与 timeout。有限 repair 仅允许语法 normalization，不得创造 semantic field/value。
- 统一错误 taxonomy：`configuration / authentication / rate_limit / timeout / connection / request / service / response_validation`。禁止 provider-specific 上层分支与 silent fallback。
- trace 至少记录 public `profile_key/provider_protocol/model/task/usage/error_class`；不得记录 API Key、Authorization、secret URL query、完整 prompt 或原始敏感响应。pricing 未配置时 `estimated_cost=null`。

#### M5.8 completion gate

固定顺序为 S1 docs/contract、S2 architecture audit、S3 profile、S4 shared provider、S5 DeepSeek migration、S6 Kimi、S7 request/conversation snapshot、S8 frontend selector、S9 error/usage/trace、S10 concurrency/switch、S11 Semantic Compatibility、S12 full regression、S13 Real DeepSeek/Kimi smoke、S14 final docs/commit/push/remote CI。

必须证明：shared provider、无 Kimi duplicate Service stack、无 global mutable default、in-flight immutable、并发 conversation 不串 profile、mid-conversation switch 保留 canonical state、malformed response fail closed、no fallback/no secret leakage；同一 semantic case contract 在 DeepSeek/Kimi 上比较 canonical/result correctness。Real API 不进入 CI Secret dependency。M5.9/M5.10 不得提前实现。

### M5.7.1 — Semantic Reliability / Regression Firewall

M5.7.1 统一处理 M5.5—M5.7 已暴露的问答语义回归、永久回归防火墙与高强度问答验收。允许修改 Intent、Object/Member/Temporal Grounding、StateTransition、semantic validation、Memory inheritance、Deterministic DAX 邻接验证和 semantic tests；禁止报表视觉、Template/Renderer Registry、LLM Provider、多模型、MCP 性能与 Resource lifecycle 改造。

永久 semantic authority 为：

```text
runtime schema
+ model-scoped metadata/glossary
+ runtime members
+ explicit user expression
+ compatible committed structured Memory
→ Semantic Grounding
→ deterministic StateTransition
→ deterministic DAX
→ QueryResult
→ VerifiedFactSet
```

日期角色解析固定优先级为：用户显式指定日期角色 → model-scoped metadata → 可由 runtime relationship/default temporal role 唯一证明的角色 → clarification。不得要求模型只存在一个 Date/DateTime 字段；无法唯一证明时必须 fail closed，不得猜测。

永久 Semantic Compatibility Gate 至少验证：已知语义形成正确 canonical slots；unknown/ambiguous object/member ZERO DAX；绝对/相对/季度/recent 时间确定性；多轮 KEEP/REPLACE/CLEAR；TopN/ranking；unsupported ZERO DAX；schema mutation fail closed；Sales/Education/Inventory/unknown holdout；production 无 benchmark-answer leakage；frontend 与 provider 无 factual/canonical semantic authority。

benchmark 问题、expected 数值、问题→答案映射不得进入 production prompt/config/glossary/regex/fallback/hidden lookup。Known-answer oracle 只能位于 test/harness 边界，并且 production runtime 不得依赖它。

### M5.7.2 — Report Template Architecture Closure

M5.7.2 状态为 COMPLETE，只负责 Report Template Gate 前移、Template/Renderer Registry、前端模板选择 UX、简易模板视觉与信息架构最终修复；M5.7.1 Semantic authority 保持冻结，未扩展到 M5.8—M5.10。

### M5.8.1 — 前置性能加速与本地 MCP 会话复用

状态为 COMPLETE。仅前移完整 M5.9 中低风险、语义透明的子集：monotonic stage profiling、application-owned Local MCP session、session 内 tool discovery cache、严格按 runtime/Desktop identity/session generation 隔离的短 TTL discovery/probe/schema cache、按 model/schema/table/field/normalized request/limit 隔离的 bounded member cache、per-key async singleflight 和最小 MCP semaphore。任何 validation failure、Desktop/PBIX identity 或 session generation 变化都必须使相关 cache 失效。

禁止 Redis、跨进程 cache、Answer/Report HTML/LLM semantic answer/QueryResult/VerifiedFactSet/DAX execution result cache，以及 Natural Language → Canonical QueryPlan cache。每个业务 turn 仍必须执行必要 DAX。M5.8 Provider、Semantic/Time/Member/TopN/StateTransition、Deterministic DAX、VerifiedFactSet、Report factual authority 与前端业务 UX 全部冻结。

### M5.8.2 — 自然语言路由与业务语义层增强

状态为 COMPLETE。Question Router 只决定产品能力类别；非业务 turn 在正式 Grounding 前返回并保持 ZERO schema/member/DAX/semantic Memory mutation。业务问题由领域无关 Query Shape 决定 required slots，canonical identity 与事实仍只来自 runtime catalog/member、Grounding/StateTransition、Deterministic DAX、QueryResult 与 VerifiedFactSet。已实现 dimension-only、Top1、runtime-validated member set/`IN_SET`、filtered aggregation、bounded trend、minimal clarification 与多轮 shape 继承。

### M5.8.3 — MCP-driven ModelSemanticContext

状态为 IN PROGRESS，未发布。任意 PBIX 自动形成 model semantic context/business binding、通用 runtime semantic adaptation 只属于本阶段；不得以 global glossary、ontology、RAG、embedding、vector DB 或 knowledge graph 绕过 runtime authority。

### M5.9 — MCP performance and resilience

M5.8.1 已前移低风险基础设施。M5.9 继续负责完整范围：

- profiling；
- session/cache 的高并发、故障与长时稳定性验证；
- 完整 bounded concurrency 与 bounded queue/backpressure；
- 20/50/100 concurrency；
- PBIX/backend restart、fault injection 与 long soak。

任何优化不得降低 schema/member/instance/factual validation，不得绕过 Grounding、Layer 3、VerifiedFactSet 或 stale fail-closed；禁止修改 Semantic/DAX/VerifiedFactSet authority。

### M5.10 — 固定专业销售报表模板与两模板选择

M5.10 必须晚于 M5.9，状态为 NOT STARTED：

- “简易模板”= 当前 `sales_report.html` 经 M5.7 可读性优化后的稳定模板；
- “销售模板”= 按已确认 Power BI 参考报表版式固定制作的专业 sales report HTML；
- 用户生成报表时可明确选择“简易模板”或“销售模板”。

固定链为：

```text
VerifiedFactSet
→ ReportData / ReportSpec
→ template_key
→ deterministic fixed HTML renderer
```

LLM 不拥有 HTML layout、factual 或 query authority，不得临场生成 HTML/CSS/SVG。专业销售模板规划包含深色 Header/title/navigation、KPI cards、左侧阶段/漏斗业务区、中部横向业务对比、右侧状态/异常/明细区、下部区域/业务表格、地域视觉、明细表、footer 指标口径与 Last Refresh。若 runtime schema 没有 Forecast/Goal/Pipeline 等事实，必须以真实可支持的 sales-specific section 替代到相同版位，禁止伪造；Agent 主链仍保持跨领域通用。只有 M5.10 完成全部正式 Gate 后才允许声明 `M5 FINAL`。

## 四、Generalization Gate

PowerBIAgent 的目标不是 Sales Agent。M5.5 及以后每个影响语义或展示泛化的版本，至少使用三个不同业务域验证：

```text
Sales / Retail
Education
Inventory / Operations
```

生产代码不得写死下列名称或对应答案，除非位于正式 model-scoped glossary 或明确 test fixture：

```text
Total Sales
Region
Product
StudentCount
AttendanceRate
InventoryTurnover
Warehouse
```

测试答案不得放入 LLM Prompt。正确 acceptance 输入链固定为：

```text
runtime schema
+ semantic metadata
+ runtime members
+ user question
→ Agent
→ QueryPlan
→ DAX
→ QueryResult
→ VerifiedFactSet
```

随后由独立 deterministic oracle 校验结果。开发期覆盖三个已知业务域；最终还必须使用主要模型之外、开发期间未知的 holdout 业务模型。至少覆盖：新字段、多相似字段、display rename、table rename、member change、glossary missing。Agent 只能 `resolve`、`clarify` 或 `no-match`，禁止猜测或 silent semantic downgrade。

## 五、里程碑隔离与完成门禁

一个 milestone 禁止同时大规模修改以下多个域：

```text
Semantic
MCP
Presentation
Report
Resource lifecycle
```

每轮固定顺序：

```text
Spec
→ Failure reproducer
→ Regression tests
→ Minimal implementation
→ Focused Real
→ Cross-domain
→ Full gates
→ User manual acceptance
→ commit
```

`1900 tests passed` 或任何单一自动化数字都不能独立支持 COMPLETE。Real Browser / 人工验收是正式 Gate；测试、Real 数据、人工视觉与用户 acceptance 必须分别记录，不能互相替代。

## 六、M5.4.2 边界

M5.4.2 只建立 `m5/rebuild` Git 基线并固化本文档及相关治理入口，不修改生产业务逻辑、不改 schema/migration、不开始新版 M5.5。完成后必须停止并等待下一轮明确指令。

## 七、M5.5 checkpoint 与完成边界

M5.5 固定顺序为 S1 docs/contracts、S2 semantic failure reproducers、S3 capability、S4 object/member、S5 multi-turn、S6 ranking/TopN、S7 temporal、S8 cross-domain/schema mutation、S9 focused regression、S10 full backend/golden/governance、S11 Real Browser/manual、S12 final docs/commit/push。任一 checkpoint FAIL 不进入下一项。

完成必须同时证明：explicit unresolved 全部 ZERO DAX/QueryResult/Memory commit；四轮 slot transition、TopN、time filter/grouping、readonly unsupported 正确；Sales/Education/Inventory、未知 holdout 与 schema mutation 全部通过；无 sales-specific production hardcode；full gates 与 Real/manual acceptance 均 PASS。

M5.5 完成证据：

- `火星区` clarification 且 ZERO DAX/QueryResult/Memory commit；`华南/华南区/南区` 通过 runtime members canonicalize 为 `South`；
- Real Rich PBIX 四轮正确完成 measure/time/filter KEEP/REPLACE 与 Product Top3 descending；
- Sales、Education、Inventory、未知 opaque holdout、schema mutation 与 capability/temporal gates 通过 deterministic oracle；
- backend `1823 passed, 1 skipped`，frontend `69 passed` 且 typecheck/lint/build PASS，Golden `11 passed, 1 manual-real skipped`，全部治理门禁与 Real Browser/manual acceptance PASS；
- acceptance automation-owned residual=0；未修改 Presentation、Resource UX、Report、MCP performance 或 M5.10 实现。

## 八、M5.6 checkpoint 与完成边界

M5.6 固定顺序为 P1 docs/contracts、P2 formatter/localization、P3 presentation density、P4 recent resource truth/sorting、P5 failed lifecycle、P6 floating menus、P7 Settings layout、P8 cross-domain、P9 focused tests、P10 full regression/governance、P11 Real Browser/manual、P12 final docs/commit/push。任一 checkpoint FAIL 不进入下一项。

完成必须同时证明：canonical/display 严格分离；scalar 去 KPI 冗余；grouped/trend Answer 不复述 table 且无 raw timestamp；Recent Reports/Settings 同 truth；Recent Conversation newest-first；failed conversation 完整 lifecycle；conversation/report menu 不裁切；Settings 长列表 action 始终可达；Sales/Education/Inventory/unknown holdout display 无 production frontend field dictionary；full gates、Rich PBIX Real/manual 与 automation-owned residual=0 全部 PASS。

## 九、M5.7 checkpoint 与完成边界

M5.7 固定顺序为 R1 docs/roadmap → R2 template-required failure reproducers → R3 backend gate → R4 frontend explicit selection → R5 responsive geometry → R6 time-axis/labels → R7 donut/table/accessibility → R8 focused regression → R9 full/golden/governance → R10 Real Browser/manual → R11 final docs/commit/push。任一 checkpoint FAIL 不进入下一项。

完成必须同时证明：missing/invalid/stale template 均在 ReportData/ReportSpec/Renderer/artifact 前 fail closed；当前 `sales_report` 正式命名为“简易模板”；1—60 points 与 390—2560 宽度可读；无时间/label clipping、页面水平滚动或巨大无意义空白；donut/legend/table/accessibility 通过；full gates、Rich PBIX Real/manual 与 automation-owned residual=0 全部 PASS。M5.5/M5.6 authority、MCP 与 LLM Provider 不变。

M5.7 已按 R1—R11 顺序完成：template-required spy 证明无模板时只有 intent recognition，ReportData/ReportSpec/Renderer/artifact 均为 0；42 组 visual matrix 与 Rich PBIX Real Browser/manual 通过；automation-owned conversation/report/HTML/SQLite/delete-intent residual=0。M5.8—M5.10 仍为 NOT STARTED，M5 FINAL 尚未成立。

## 十、M5.7.1 checkpoint 与完成边界

固定顺序为 S1 docs/contract、S2 repository semantic audit、S3 known regression reproducers、S4 temporal/date-role fix、S5 object/member/ambiguity、S6 multi-turn/ranking/capability、S7 property/metamorphic stress、S8 cross-domain/schema mutation/holdout、S9 permanent Semantic Compatibility Gate、S10 focused/backend/golden/governance、S11 Rich PBIX Real/manual、S12 final docs/commit/push。任一 checkpoint FAIL 不进入下一项。

完成必须同时证明：`2025年5月销售额` 正确执行；多日期模型在默认角色可证明时解析、否则 clarification；unknown member 不 fallback；多轮 slot 不丢失；TopN/ranking 正确；unsupported ZERO DAX；Sales/Education/Inventory/unknown holdout 与 schema mutation PASS；stress/property suite 和 no-answer-leakage PASS；full regression、Rich PBIX manual 与 automation residual=0；M5.5 authority 未弱化，且未开发 M5.7.2/M5.8+。

M5.7.1 已按 S1—S12 完成：production-path reproducer 证明旧逻辑在 Rich 多日期模型错误依赖 cardinality；最终 date-role resolver 固定为显式角色 → 唯一 `temporal_role: default` → 唯一 temporal-grouping binding → 唯一 glossary 日期对象 → 唯一 runtime 日期字段 → clarification。Semantic Compatibility `302 passed`，backend `1901 passed, 1 skipped`，frontend `80 passed` 且 build PASS，Golden `11 passed, 1 manual-real skipped`，跨域/schema mutation、no-answer-leakage、Rich PBIX Real/manual 与 automation residual=0 均通过。M5.5 authority 保持不变，M5.7.2 / M5.8—M5.10 仍未开始。

## 十一、M5.7.2 checkpoint 与完成边界

M5.7.2 已完成 Intent 后集中 Template Gate、Template/Renderer Registry 与 Dispatcher、只读后端模板目录、后端目录驱动的前端显式选择，以及简易模板信息架构和时间轴收口。missing/unknown/stale template 统一精确提示并保持 ZERO schema/QueryPlan/DAX/Power BI/ReportData/ReportSpec/Renderer/artifact；无 default、猜测或 first-item fallback。完整 deterministic fixture 在 390/768/1440/2560 覆盖 4 KPI、15 点趋势、区域、品类、Top 产品、关键明细和 footer，均无水平滚动或标签碰撞；Real runtime 仅渲染 schema 可证明的 section，缺失 Region/Product/Customer 时 deterministic omit。Semantic Compatibility `304 passed`，backend `1918 passed, 1 skipped`，frontend `83 passed` 且 typecheck/lint/build PASS，Golden `11 passed, 1 manual-real skipped`，automation-owned residual=0。未修改 M5.7.1 authority，未开发 M5.8/M5.9/M5.10。

M5.8 已完成共享 OpenAI-compatible Provider、不可变 DeepSeek/Kimi profiles、显式 request/conversation snapshot selection、统一 error/usage/trace 与 backend-owned frontend selector。Rich PBIX 双模型同题集的 canonical plan 与规范化 QueryResult 一致；并发隔离、mid-conversation switch、unknown/unsupported、固定 `sales_report`、profile mismatch=0 与 residual=0 通过。Fresh Semantic Compatibility `306 passed`，backend `1940 passed, 1 skipped`，frontend `86 passed` 且 typecheck/lint/build PASS，Golden `11 passed, 1 manual-real skipped`，全部治理与 compileall PASS。未修改 Semantic/DAX/VerifiedFactSet、M5.7.2 Report 或 MCP；M5.9/M5.10 未开发。

M5.8.1 已完成 application-owned Local MCP session、session-local tool discovery、identity/generation/fingerprint-scoped metadata/member TTL cache、cancellation-safe singleflight、最小 bounded concurrency 与安全 monotonic stage trace。优化后 metadata discovery cold/warm `3782/0ms`、schema `422/156ms`、member `515/172ms`，DAX 两次真实执行 `485/515ms`；full-turn 冷启动旅程 `18172ms`，稳定热态 10 轮 `13000ms`，4 路小并发 `3719ms`。Rich PBIX canonical plan/DAX/QueryResult/Memory/Report 不变且 residual=0；Semantic Compatibility `306 passed`、backend `1950 passed, 1 skipped`、frontend `86 passed`、Golden `11 passed, 1 manual-real skipped` 与全部治理通过。未引入 Redis 或 factual/semantic result cache，未开发 M5.8.2、完整 M5.9 或 M5.10。

M5.8.2 已完成 Question Router、八类通用 Query Shape、shape-specific clarification、安全 calculator/help/system-info、dimension-only distinct、Top1、runtime-validated `IN_SET` 与 bounded month range。Sales/Education/Inventory/unknown holdout、schema mutation、unknown/unresolved ZERO DAX 与 15 项 Rich PBIX Real 题集通过，residual=0；Semantic Compatibility `421 passed`、backend `2046 passed, 1 skipped`、frontend `86 passed`、Golden `11 passed, 1 manual-real skipped` 与全部治理通过。M5.8.3/M5.9/M5.10 未开发，M5 FINAL=false。

---

*创建日期：2026-08-26 | 最后更新：2026-09-02 M5.8 / M5.8.1 / M5.8.2 / M5.8.3 / M5.8.4 COMPLETE；M5.9 / M5.10 NOT STARTED；M5 FINAL 尚未成立*
